from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.services.blob_storage_service import (
    copy_blobs_between_containers,
    delete_blob,
    list_blob_files,
    sync_blob_prefix_to_local,
    sync_local_directory_to_blob,
)
from api.services.config import append_publish_log_entry, sync_next_prod_chroma_from_main, update_prod_config, update_prod_config
from api.services.database_regeneration_service import run_full_regeneration

REPO_ROOT = Path(__file__).resolve().parents[2]

_publish_state_lock = threading.Lock()
_publish_cancel_event = threading.Event()
_publish_state: dict[str, Any] = {
    "status": "idle",
    "running": False,
    "cancel_requested": False,
    "progress": 0,
    "message": "Idle",
    "message_key": "publish.status.idle",
    "operation": "publish",
    "model": None,
    "provider": None,
    "uploaded_files_count": 0,
    "updated_at": None,
    "error": None,
    "error_key": "publish.status.error",
    "result": None,
}


def _request_publish_cancel() -> None:
    _publish_cancel_event.set()
    _set_publish_state(
        cancel_requested=True,
        status="cancelling",
        running=True,
        message="Cancellation requested.",
        message_key="publish.status.cancelRequested",
    )


def _is_publish_cancel_requested() -> bool:
    return _publish_cancel_event.is_set()


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _set_publish_state(**updates: Any) -> None:
    with _publish_state_lock:
        _publish_state.update(updates)
        _publish_state["updated_at"] = datetime.now(timezone.utc).isoformat()


# Purpose: Retrieve data needed by callers and return it in a ready-to-use format.
# Inputs/Outputs: See signature and return annotation for contract details.
def get_publish_status() -> dict[str, Any]:
    with _publish_state_lock:
        state = dict(_publish_state)
    return {
        "status": state.get("status", "idle"),
        "running": bool(state.get("running", False)),
        "cancel_requested": bool(state.get("cancel_requested", False)),
        "progress": int(state.get("progress", 0) or 0),
        "message": state.get("message", "Idle"),
        "message_key": state.get("message_key", "publish.status.idle"),
        "operation": state.get("operation", "publish"),
        "model": state.get("model"),
        "provider": state.get("provider"),
        "uploaded_files_count": int(state.get("uploaded_files_count", 0) or 0),
        "updated_at": state.get("updated_at"),
        "error": state.get("error"),
        "error_key": state.get("error_key", "publish.status.error"),
        "result": state.get("result"),
    }


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _clear_blob_destination(container_name: str, prefix: str = "") -> int:
    prefix_value = (prefix or "").strip("/") or None
    blobs = list_blob_files(prefix=prefix_value, container_name=container_name)
    removed = 0
    for blob in blobs:
        delete_blob(blob.name, container_name=container_name)
        removed += 1
    return removed


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _run_publish_job(model: str, provider: str) -> None:
    try:
        _publish_cancel_event.clear()
        _set_publish_state(
            status="running",
            running=True,
            cancel_requested=False,
            progress=5,
            message="Preparing publication...",
            message_key="publish.status.preparing",
            operation="publish",
            model=model,
            provider=provider,
            error=None,
            error_key="publish.status.error",
            result=None,
        )

        if _is_publish_cancel_requested():
            raise RuntimeError("Publication cancelled by user.")

        main_container = os.getenv("AZURE_MAIN_KB_CONTAINER", "nutrifaq-dbase-main").strip()
        prev_container = os.getenv("AZURE_PREV_KB_CONTAINER", "nutrifaq-dbase-prev").strip()
        local_main_root = REPO_ROOT / os.getenv("AZURE_KB_MAIN_LOCAL_ROOT", "nutrifaq-dbase-main")

        if not local_main_root.exists():
            raise ValueError(f"Local main KB folder not found: {local_main_root}")
        if _is_publish_cancel_requested():
            raise RuntimeError("Publication cancelled by user.")

        documents_root = local_main_root / "documents"
        documents_file_count = sum(1 for path in documents_root.rglob("*") if path.is_file()) if documents_root.exists() else 0
        
        # _set_publish_state(
        #     progress=20,
        #     message="Regenerating local database...",
        #     message_key="publish.status.regeneratingDb",
        # )
        # if _is_publish_cancel_requested():
        #     raise RuntimeError("Publication cancelled by user.")
        # # Regenerate the local database before backing up the current main database
        # regeneration_result = run_full_regeneration(
        #     include_extract_docx=False,
        #     include_extract_references=False,
        #     root_folder=local_main_root.name,
        #     container_name=main_container,
        # )
        # if regeneration_result.get("status") != "success":
        #     raise RuntimeError(
        #         f"Database regeneration failed before backup: {regeneration_result.get('message', 'unknown error')}"
        #     )

        backup_result = {"copied_count": 0, "failed_count": 0}
        _set_publish_state(
            progress=35,
            message="Backing up current database...",
            message_key="publish.status.backingUp",
        )
        if _is_publish_cancel_requested():
            raise RuntimeError("Publication cancelled by user.")
        # Backup the current main database to the previous container
        backup_result = copy_blobs_between_containers(
            source_container=main_container,
            destination_container=prev_container,
            overwrite=True,
            wait_for_completion=True,
        )

        _set_publish_state(
            progress=60,
            message="Saving new database...",
            message_key="publish.status.savingDatabase",
        )
        if _is_publish_cancel_requested():
            raise RuntimeError("Publication cancelled by user.")
        # Sync local main KB folder to the main container in Azure Blob Storage
        sync_local_directory_to_blob(
            source_root=local_main_root,
            destination_prefix="",
            overwrite=True,
            container_name=main_container,
        )

        _set_publish_state(
            progress=80,
            message="Updating production database...",
            message_key="publish.status.updatingProduction",
        )
        if _is_publish_cancel_requested():
            raise RuntimeError("Publication cancelled by user.")

        # Sync the next production Chroma database from the main database
        source_chroma, target_chroma, old_prod_sqlite, new_prod_sqlite = sync_next_prod_chroma_from_main(provider, model)

        _set_publish_state(
            progress=95,
            message="Writing publish log...",
            message_key="publish.status.writingLog",
        )
        publish_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": "publish",
            "model": model,
            "provider": provider,
            "model_used": model,
            "provider_used": provider,
            "files_count": documents_file_count,
            "old_prod_sqlite": old_prod_sqlite,
            "new_prod_sqlite": new_prod_sqlite,
            "source_chroma": str(source_chroma),
            "target_chroma": str(target_chroma),
            "main_container": main_container,
            "prev_container": prev_container,
        }
        append_publish_log_entry(publish_entry)

        result = {
            "status": "ok",
            "message": "Publication completed.",
            "publish": publish_entry,
            "backup": {
                "copied_count": backup_result.get("copied_count", 0),
                "failed_count": backup_result.get("failed_count", 0),
            },
            "uploaded_files_count": documents_file_count,
        }

        _set_publish_state(
            status="completed",
            running=False,
            progress=100,
            message="Publication completed.",
            message_key="publish.status.completed",
            operation="publish",
            uploaded_files_count=documents_file_count,
            result=result,
            error=None,
            error_key="publish.status.error",
        )
    except Exception as exc:
        cancelled = _is_publish_cancel_requested()
        _set_publish_state(
            status="cancelled" if cancelled else "error",
            running=False,
            cancel_requested=False,
            progress=100,
            message="Publication cancelled." if cancelled else f"Unable to publish: {exc}",
            message_key="publish.status.cancelRequested" if cancelled else "publish.status.error",
            operation="publish",
            error=None if cancelled else str(exc),
            error_key="publish.status.error",
            result=None,
        )
        _publish_cancel_event.clear()


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _run_revert_job() -> None:
    try:
        _set_publish_state(
            status="running",
            running=True,
            progress=5,
            message="Preparing restore...",
            message_key="publish.revert.preparing",
            operation="revert",
            model=None,
            provider=None,
            error=None,
            error_key="publish.status.error",
            result=None,
        )

        main_container = os.getenv("AZURE_MAIN_KB_CONTAINER", "nutrifaq-dbase-main").strip()
        prev_container = os.getenv("AZURE_PREV_KB_CONTAINER", "nutrifaq-dbase-prev").strip()
        local_main_root = REPO_ROOT / os.getenv("AZURE_KB_MAIN_LOCAL_ROOT", "nutrifaq-dbase-main")

        if not local_main_root.exists():
            raise ValueError(f"Local main KB folder not found: {local_main_root}")

        _set_publish_state(
            progress=20,
            message="Restoring previous database...",
            message_key="publish.revert.restoringPrevious",
        )
        copy_blobs_between_containers(
            source_container=prev_container,
            destination_container=main_container,
            overwrite=True,
            wait_for_completion=True,
        )

        _set_publish_state(
            progress=55,
            message="Restoring main database...",
            message_key="publish.revert.restoringMain",
        )
        sync_blob_prefix_to_local(
            prefix="",
            local_root=local_main_root,
            remove_existing=True,
            container_name=main_container,
        )

        _set_publish_state(
            progress=75,
            message="Updating production database...",
            message_key="publish.revert.updatingProduction",
        )
        source_chroma, target_chroma, old_prod_sqlite, new_prod_sqlite = sync_next_prod_chroma_from_main()

        _set_publish_state(
            progress=90,
            message="Writing publish log...",
            message_key="publish.revert.writingLog",
        )
        revert_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": "revert",
            "source_container": prev_container,
            "destination_container": main_container,
            "files_count": sum(1 for path in local_main_root.rglob("*") if path.is_file()),
            "old_prod_sqlite": old_prod_sqlite,
            "new_prod_sqlite": new_prod_sqlite,
            "source_chroma": str(source_chroma),
            "target_chroma": str(target_chroma),
            "main_container": main_container,
            "prev_container": prev_container,
        }
        append_publish_log_entry(revert_entry)

        result = {
            "status": "ok",
            "message": "Restauration terminée.",
            "revert": revert_entry,
            "uploaded_files_count": revert_entry["files_count"],
        }

        _set_publish_state(
            status="completed",
            running=False,
            progress=100,
            message="Restore completed.",
            message_key="publish.revert.completed",
            operation="revert",
            uploaded_files_count=revert_entry["files_count"],
            result=result,
            error=None,
            error_key="publish.status.error",
        )
    except Exception as exc:
        _set_publish_state(
            status="error",
            running=False,
            progress=100,
            message=f"Restore failed: {exc}",
            message_key="publish.revert.error",
            operation="revert",
            error=str(exc),
            error_key="publish.revert.error",
            result=None,
        )


# Purpose: Implement a focused unit of backend behavior used by routes or services.
# Inputs/Outputs: See signature and return annotation for contract details.
def cancel_publish() -> dict[str, Any]:
    with _publish_state_lock:
        if not bool(_publish_state.get("running")):
            return {
                "status": "idle",
                "message": "No publish is currently running.",
                "message_key": "publish.status.idle",
            }
    _request_publish_cancel()
    return {
        "status": "cancelling",
        "message": "Cancellation requested.",
        "message_key": "publish.status.cancelRequested",
    }


def start_publish(model: str, provider: str) -> dict[str, Any]:
    with _publish_state_lock:
        if bool(_publish_state.get("running")):
            raise RuntimeError("A publish is already running.")

    _publish_cancel_event.clear()
    thread = threading.Thread(
        target=_run_publish_job,
        args=(model, provider),
        name="publish-job",
        daemon=True,
    )
    thread.start()
    _set_publish_state(
        status="queued",
        running=True,
        cancel_requested=False,
        progress=0,
        message="Publication started in background.",
        message_key="publish.status.started",
        operation="publish",
        model=model,
        provider=provider,
        error=None,
        error_key="publish.status.error",
        result=None,
    )
    return {
        "status": "accepted",
        "message": "Publication started in background.",
        "message_key": "publish.status.started",
        "model": model,
        "provider": provider,
    }


# Purpose: Implement a focused unit of backend behavior used by routes or services.
# Inputs/Outputs: See signature and return annotation for contract details.
def start_revert() -> dict[str, Any]:
    with _publish_state_lock:
        if bool(_publish_state.get("running")):
            raise RuntimeError("A revert is already running.")

    _publish_cancel_event.clear()
    thread = threading.Thread(
        target=_run_revert_job,
        name="publish-revert-job",
        daemon=True,
    )
    thread.start()
    _set_publish_state(
        status="queued",
        running=True,
        cancel_requested=False,
        progress=0,
        message="Restore started in background.",
        message_key="publish.revert.started",
        operation="revert",
        model=None,
        provider=None,
        error=None,
        error_key="publish.status.error",
        result=None,
    )
    return {
        "status": "accepted",
        "message": "Restore started in background.",
        "message_key": "publish.revert.started",
    }

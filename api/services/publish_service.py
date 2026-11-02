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
from api.services.config import (
    append_publish_log_entry,
    load_publish_schedule_entries,
    sync_next_prod_chroma_from_main,
    update_prod_config,
    update_prod_config,
)
from api.services.indexation_service import get_indexation_status, run_full_indexation
from api.services.workflow_events import emit_workflow_event

REPO_ROOT = Path(__file__).resolve().parents[2]

_publish_state_lock = threading.Lock()
_publish_cancel_event = threading.Event()
_publish_state: dict[str, Any] = {
    "status": "idle",
    "step": "idle",
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
    "details": {},
}


def _request_publish_cancel() -> None:
    _publish_cancel_event.set()
    _set_publish_state(
        cancel_requested=True,
        status="cancelling",
        step="cancelling",
        running=True,
        message="Cancellation requested.",
        message_key="publish.status.cancelRequested",
    )


def _is_publish_cancel_requested() -> bool:
    return _publish_cancel_event.is_set()


def _next_scheduled_publication_at() -> str | None:
    try:
        entries = load_publish_schedule_entries()
    except Exception:
        return None

    next_run: datetime | None = None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if not bool(entry.get("enabled", True)):
            continue
        if bool(entry.get("immediate")):
            continue

        run_at_raw = str(entry.get("run_at") or "").strip()
        if not run_at_raw:
            continue
        normalized = run_at_raw[:-1] + "+00:00" if run_at_raw.endswith("Z") else run_at_raw
        try:
            run_at = datetime.fromisoformat(normalized)
        except ValueError:
            continue
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        run_at = run_at.astimezone(timezone.utc)
        if next_run is None or run_at < next_run:
            next_run = run_at

    return next_run.isoformat() if next_run is not None else None


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _set_publish_state(**updates: Any) -> None:
    snapshot: dict[str, Any]
    with _publish_state_lock:
        _publish_state.update(updates)
        _publish_state["updated_at"] = datetime.now(timezone.utc).isoformat()
        snapshot = dict(_publish_state)
        details = snapshot.get("details")
        snapshot["details"] = details if isinstance(details, dict) else {}
    emit_workflow_event("publish.state", snapshot)


# Purpose: Retrieve data needed by callers and return it in a ready-to-use format.
# Inputs/Outputs: See signature and return annotation for contract details.
def get_publish_status() -> dict[str, Any]:
    with _publish_state_lock:
        state = dict(_publish_state)
    details = state.get("details")
    if not isinstance(details, dict):
        details = {}
    indexation = get_indexation_status()
    next_publication_at = _next_scheduled_publication_at()
    status_value = str(state.get("status", "idle"))
    finished_at = state.get("updated_at") if status_value in {"completed", "cancelled", "error"} else None
    return {
        "status": status_value,
        "step": state.get("step", "idle"),
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
        "details": details,
        "next_publication_at": next_publication_at,
        "finished_at": finished_at,
        "indexation": indexation,
        "workflow_steps": [
            {
                "key": "next_publication",
                "label": "Prochaine publication",
                "status": "scheduled" if next_publication_at else "none",
                "at": next_publication_at,
            },
            {
                "key": "indexation",
                "label": "Indexation",
                "status": "running" if bool(indexation.get("running")) else "idle",
                "current_step": indexation.get("current_step"),
                "current_step_label": indexation.get("current_step_label"),
            },
            {
                "key": "publication",
                "label": "Publication",
                "status": status_value,
                "step": state.get("step", "idle"),
                "progress": int(state.get("progress", 0) or 0),
            },
            {
                "key": "finished",
                "label": "Terminé",
                "status": "done" if finished_at else "pending",
                "at": finished_at,
            },
        ],
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
        append_publish_log_entry({
            "timestamp": datetime.now().astimezone().isoformat(),
            "operation": "publish",
            "status": "started",
            "model": model,
            "provider": provider,
            "message": "Publication started.",
        })
        _set_publish_state(
            status="running",
            step="preparing",
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
            details={"stage": "preparing"},
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
 
        backup_result = {"copied_count": 0, "failed_count": 0}


        # def _on_backup_file_transferred(progress_info: dict[str, Any]) -> None:
        #     if _is_publish_cancel_requested():
        #         return
        #     transfer_current = int(progress_info.get("index") or 0)
        #     transfer_total = int(progress_info.get("total") or 0)
        #     transfer_progress = 0
        #     if transfer_total > 0:
        #         transfer_progress = max(0, min(100, int(round((transfer_current / transfer_total) * 100))))
        #     source_blob_name = str(progress_info.get("source_blob_name") or "").strip()
        #     transfer_file = source_blob_name.split("/")[-1] if source_blob_name else ""
        #     _set_publish_state(
        #         progress=transfer_progress,
        #         step="backing_up",
        #         message="Backing up current database...",
        #         message_key="publish.status.backingUp",
        #         details={
        #             "stage": "backing_up",
        #             "main_container": main_container,
        #             "backup_container": prev_container,
        #             "documents_file_count": documents_file_count,
        #             "transfer_phase": "backup",
        #             "transfer_current": transfer_current,
        #             "transfer_total": transfer_total,
        #             "transfer_file": transfer_file,
        #         },
        #     )

        # if _is_publish_cancel_requested():
        #     raise RuntimeError("Publication cancelled by user.")
        # # Backup the current main database to the previous container
        # backup_result = copy_blobs_between_containers(
        #     source_container=main_container,
        #     destination_container=prev_container,
        #     overwrite=True,
        #     wait_for_completion=True,
        #     is_cancel_requested=_is_publish_cancel_requested,
        #     on_file_transferred=_on_backup_file_transferred,
        # )
        # if backup_result.get("cancelled"):
        #     raise RuntimeError("Publication cancelled by user.")


        if _is_publish_cancel_requested():
            raise RuntimeError("Publication cancelled by user.")

        def _on_upload_file_transferred(progress_info: dict[str, Any]) -> None:
            if _is_publish_cancel_requested():
                return
            transfer_current = int(progress_info.get("index") or 0)
            transfer_total = int(progress_info.get("total") or 0)
            transfer_progress = 0
            if transfer_total > 0:
                transfer_progress = max(0, min(100, int(round((transfer_current / transfer_total) * 100))))
            source_path_value = str(progress_info.get("source_path") or "").replace("\\", "/").strip()
            transfer_file = source_path_value.split("/")[-1] if source_path_value else ""
            _set_publish_state(
                progress=transfer_progress,
                step="saving_database",
                message="Saving new database...",
                message_key="publish.status.savingDatabase",
                details={
                    "stage": "saving_database",
                    "main_container": main_container,
                    "local_main_root": str(local_main_root),
                    "transfer_phase": "saving_database",
                    "transfer_current": transfer_current,
                    "transfer_total": transfer_total,
                    "transfer_file": transfer_file,
                },
            )

        # Sync local main KB folder to the main container in Azure Blob Storage
        sync_local_directory_to_blob(
            source_root=local_main_root,
            destination_prefix="",
            clear_destination_first=True,
            overwrite=True,
            container_name=main_container,
            is_cancel_requested=_is_publish_cancel_requested,
            on_file_transferred=_on_upload_file_transferred,
        )

        _set_publish_state(
            progress=99,
            step="updating_production",
            message="Updating production database...",
            message_key="publish.status.updatingProduction",
            details={"stage": "updating_production"},
        )
        if _is_publish_cancel_requested():
            raise RuntimeError("Publication cancelled by user.")

        # Sync the next production Chroma database from the main database
        source_chroma, target_chroma, old_prod_sqlite, new_prod_sqlite = sync_next_prod_chroma_from_main(
            provider,
            model,
            is_cancel_requested=_is_publish_cancel_requested,
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
            step="completed",
            running=False,
            progress=100,
            message="Publication completed.",
            message_key="publish.status.completed",
            operation="publish",
            uploaded_files_count=documents_file_count,
            result=result,
            error=None,
            error_key="publish.status.error",
            details={
                "stage": "completed",
                "documents_file_count": documents_file_count,
                "main_container": main_container,
                "backup_container": prev_container,
                "backup_copied_count": backup_result.get("copied_count", 0),
                "backup_failed_count": backup_result.get("failed_count", 0),
            },
        )
        append_publish_log_entry({
            "timestamp": datetime.now().astimezone().isoformat(),
            "operation": "publish",
            "status": "completed",
            "model": model,
            "provider": provider,
            "message": "Publication completed.",
            "files_count": documents_file_count,
            "result": result,
        })
        return result
    except Exception as exc:
        cancelled = _is_publish_cancel_requested()
        _set_publish_state(
            status="cancelled" if cancelled else "error",
            step="cancelled" if cancelled else "failed",
            running=False,
            cancel_requested=False,
            progress=100,
            message="Publication cancelled." if cancelled else f"Unable to publish: {exc}",
            message_key="publish.status.cancelRequested" if cancelled else "publish.status.error",
            operation="publish",
            error=None if cancelled else str(exc),
            error_key="publish.status.error",
            result=None,
            details={
                "stage": "cancelled" if cancelled else "failed",
                "cancelled": cancelled,
                "error": None if cancelled else str(exc),
            },
        )
        append_publish_log_entry({
            "timestamp": datetime.now().astimezone().isoformat(),
            "operation": "publish",
            "status": "cancelled" if cancelled else "error",
            "model": model,
            "provider": provider,
            "message": "Publication cancelled." if cancelled else f"Unable to publish: {exc}",
            "error": None if cancelled else str(exc),
        })
        _publish_cancel_event.clear()


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _run_revert_job() -> None:
    try:
        _set_publish_state(
            status="running",
            step="preparing",
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
            details={"stage": "preparing"},
        )

        main_container = os.getenv("AZURE_MAIN_KB_CONTAINER", "nutrifaq-dbase-main").strip()
        prev_container = os.getenv("AZURE_PREV_KB_CONTAINER", "nutrifaq-dbase-prev").strip()
        local_main_root = REPO_ROOT / os.getenv("AZURE_KB_MAIN_LOCAL_ROOT", "nutrifaq-dbase-main")

        if not local_main_root.exists():
            raise ValueError(f"Local main KB folder not found: {local_main_root}")

        _set_publish_state(
            progress=20,
            step="restoring_previous",
            message="Restoring previous database...",
            message_key="publish.revert.restoringPrevious",
            details={"stage": "restoring_previous"},
        )
        copy_blobs_between_containers(
            source_container=prev_container,
            destination_container=main_container,
            overwrite=True,
            wait_for_completion=True,
        )

        _set_publish_state(
            progress=55,
            step="restoring_main",
            message="Restoring main database...",
            message_key="publish.revert.restoringMain",
            details={"stage": "restoring_main"},
        )
        sync_blob_prefix_to_local(
            prefix="",
            local_root=local_main_root,
            remove_existing=True,
            container_name=main_container,
        )

        _set_publish_state(
            progress=75,
            step="updating_production",
            message="Updating production database...",
            message_key="publish.revert.updatingProduction",
            details={"stage": "updating_production"},
        )
        source_chroma, target_chroma, old_prod_sqlite, new_prod_sqlite = sync_next_prod_chroma_from_main(
            is_cancel_requested=_is_publish_cancel_requested
        )

        _set_publish_state(
            progress=90,
            step="writing_log",
            message="Writing publish log...",
            message_key="publish.revert.writingLog",
            details={"stage": "writing_log"},
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
            step="completed",
            running=False,
            progress=100,
            message="Restore completed.",
            message_key="publish.revert.completed",
            operation="revert",
            uploaded_files_count=revert_entry["files_count"],
            result=result,
            error=None,
            error_key="publish.status.error",
            details={
                "stage": "completed",
                "files_count": revert_entry["files_count"],
                "main_container": main_container,
                "previous_container": prev_container,
            },
        )
    except Exception as exc:
        _set_publish_state(
            status="error",
            step="failed",
            running=False,
            progress=100,
            message=f"Restore failed: {exc}",
            message_key="publish.revert.error",
            operation="revert",
            error=str(exc),
            error_key="publish.revert.error",
            result=None,
            details={"stage": "failed", "error": str(exc)},
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
        step="queued",
        running=True,
        cancel_requested=False,
        progress=0,
        message="Revert started in background.",
        message_key="publish.revert.started",
        operation="revert",
        model=None,
        provider=None,
        error=None,
        error_key="publish.status.error",
        result=None,
        details={"stage": "queued"},
    )
    return {
        "status": "accepted",
        "message": "Revert started in background.",
        "message_key": "publish.revert.started",
    }

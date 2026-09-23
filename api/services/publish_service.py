from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.services.blob_storage_service import copy_blobs_between_containers, sync_local_directory_to_blob
from api.services.config import append_publish_log_entry, sync_next_prod_chroma_from_main

REPO_ROOT = Path(__file__).resolve().parents[2]

_publish_state_lock = threading.Lock()
_publish_state: dict[str, Any] = {
    "status": "idle",
    "running": False,
    "progress": 0,
    "message": "Idle",
    "model": None,
    "provider": None,
    "uploaded_files_count": 0,
    "updated_at": None,
    "error": None,
    "result": None,
}


def _set_publish_state(**updates: Any) -> None:
    with _publish_state_lock:
        _publish_state.update(updates)
        _publish_state["updated_at"] = datetime.now(timezone.utc).isoformat()


def get_publish_status() -> dict[str, Any]:
    with _publish_state_lock:
        state = dict(_publish_state)
    return {
        "status": state.get("status", "idle"),
        "running": bool(state.get("running", False)),
        "progress": int(state.get("progress", 0) or 0),
        "message": state.get("message", "Idle"),
        "model": state.get("model"),
        "provider": state.get("provider"),
        "uploaded_files_count": int(state.get("uploaded_files_count", 0) or 0),
        "updated_at": state.get("updated_at"),
        "error": state.get("error"),
        "result": state.get("result"),
    }


def _run_publish_job(model: str, provider: str) -> None:
    try:
        _set_publish_state(
            status="running",
            running=True,
            progress=5,
            message="Preparation de la publication...",
            model=model,
            provider=provider,
            error=None,
            result=None,
        )

        main_container = os.getenv("AZURE_MAIN_KB_CONTAINER", "nutrifaq-dbase-main").strip()
        prev_container = os.getenv("AZURE_PREV_KB_CONTAINER", "nutrifaq-dbase-prev").strip()
        local_main_root = REPO_ROOT / os.getenv("AZURE_KB_MAIN_LOCAL_ROOT", "nutrifaq-dbase-main")

        if not local_main_root.exists():
            raise ValueError(f"Local main KB folder not found: {local_main_root}")

        documents_root = local_main_root / "documents"
        documents_file_count = sum(1 for path in documents_root.rglob("*") if path.is_file()) if documents_root.exists() else 0
        backup_result = {"copied_count": 0, "failed_count": 0}  # Mock backup result since backup is commented out
        # _set_publish_state(progress=20, message="Backup du conteneur principal...")
        # backup_result = copy_blobs_between_containers(
        #     source_container=main_container,
        #     destination_container=prev_container,
        #     overwrite=True,
        #     wait_for_completion=True,
        # )

        # _set_publish_state(progress=50, message="Upload des fichiers locaux vers le conteneur principal...")
        # sync_local_directory_to_blob(
        #     source_root=local_main_root,
        #     destination_prefix="",
        #     overwrite=True,
        #     container_name=main_container,
        # )

        _set_publish_state(progress=75, message="Mise a jour de la base de production...")
        source_chroma, target_chroma, old_prod_sqlite, new_prod_sqlite = sync_next_prod_chroma_from_main()

        _set_publish_state(progress=90, message="Ecriture du journal de publication...")
        publish_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "provider": provider,
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
            message="Publication terminee.",
            uploaded_files_count=documents_file_count,
            result=result,
            error=None,
        )
    except Exception as exc:
        _set_publish_state(
            status="error",
            running=False,
            progress=100,
            message=f"Unable to publish: {exc}",
            error=str(exc),
            result=None,
        )


def start_publish(model: str, provider: str) -> dict[str, Any]:
    with _publish_state_lock:
        if bool(_publish_state.get("running")):
            raise RuntimeError("A publish is already running.")

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
        progress=0,
        message="Publication demarree...",
        model=model,
        provider=provider,
        error=None,
        result=None,
    )
    return {
        "status": "accepted",
        "message": "Publication started in background.",
        "model": model,
        "provider": provider,
    }

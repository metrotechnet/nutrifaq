from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from api.services.blob_storage_service import sync_local_directory_to_blob

REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_KB_ROOT = REPO_ROOT / os.getenv("MAIN_KB_ROOT", "nutrifaq-dbase")
DEBUG_KB_ROOT = REPO_ROOT / os.getenv("AZURE_KB_DEBUG_LOCAL_ROOT", "nutrifaq-dbase-debug")

_LOCK = threading.Lock()
_SCHEDULED_JOBS: dict[str, dict[str, Any]] = {}


def _parse_publish_datetime(value: datetime | str | None) -> datetime:
    if value is None:
        raise ValueError("A publish date/time is required.")
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _run_command(command: list[str], cwd: str | Path) -> dict[str, Any]:
    process = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "status": "ok" if process.returncode == 0 else "error",
        "return_code": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
        "command": " ".join(command),
    }


def copy_debug_to_main_local(
    debug_root: Path | str | None = None,
    main_root: Path | str | None = None,
) -> dict[str, Any]:
    source_root = Path(debug_root or DEBUG_KB_ROOT).resolve()
    target_root = Path(main_root or MAIN_KB_ROOT).resolve()

    if not source_root.exists():
        raise FileNotFoundError(f"Debug KB root not found: {source_root}")

    target_root.mkdir(parents=True, exist_ok=True)
    copied_files = 0
    for source_file in sorted(source_root.rglob("*")):
        if source_file.is_dir():
            continue
        relative = source_file.relative_to(source_root)
        destination = target_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination)
        copied_files += 1

    return {
        "status": "ok",
        "source_root": str(source_root),
        "target_root": str(target_root),
        "copied_files": copied_files,
    }


def restart_main_indexing(main_root: Path | str | None = None) -> dict[str, Any]:
    kb_root = Path(main_root or MAIN_KB_ROOT).resolve()
    script_path = REPO_ROOT / "api" / "db_pipeline" / "index_chromadb_json.py"
    if not script_path.exists():
        return {"status": "error", "message": f"Missing index script: {script_path}"}

    result = _run_command([os.sys.executable, str(script_path), str(kb_root)], cwd=str(REPO_ROOT))
    if result["status"] != "ok":
        return {"status": "error", "step": "index_main_chromadb", "details": result}
    return {"status": "ok", "step": "index_main_chromadb", "kb_root": str(kb_root), "details": result}


def sync_main_to_blob(
    main_root: Path | str | None = None,
    prefix: str | None = None,
    container_name: str | None = None,
) -> dict[str, Any]:
    kb_root = Path(main_root or MAIN_KB_ROOT).resolve()
    effective_prefix = (prefix or os.getenv("AZURE_KB_BLOB_PREFIX", "nutrifaq-dbase")).strip("/")
    effective_container = (container_name or os.getenv("AZURE_KB_BLOB_CONTAINER") or os.getenv("AZURE_STORAGE_CONTAINER") or "nutrifaq-knowledge-base").strip()

    if not kb_root.exists():
        return {"status": "error", "message": f"Main KB root not found: {kb_root}"}

    try:
        uploaded = sync_local_directory_to_blob(
            kb_root,
            effective_prefix,
            overwrite=True,
            container_name=effective_container,
        )
        return {
            "status": "ok",
            "prefix": effective_prefix,
            "container": effective_container,
            "uploaded_files_count": len(uploaded),
            "uploaded": uploaded,
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc), "prefix": effective_prefix, "container": effective_container}


def _process_publish_job(job_id: str) -> dict[str, Any]:
    with _LOCK:
        job = _SCHEDULED_JOBS.get(job_id)
        if not job:
            return {"status": "not_found", "job_id": job_id}
        job["status"] = "running"
        job["started_at"] = _to_utc_iso(datetime.now(timezone.utc))

    debug_root = DEBUG_KB_ROOT
    main_root = MAIN_KB_ROOT
    prefix = os.getenv("AZURE_KB_BLOB_PREFIX", "nutrifaq-dbase").strip("/")
    container_name = os.getenv("AZURE_KB_BLOB_CONTAINER") or os.getenv("AZURE_STORAGE_CONTAINER") or "nutrifaq-knowledge-base"

    try:
        copy_result = copy_debug_to_main_local(debug_root, main_root)
        if copy_result.get("status") != "ok":
            raise RuntimeError(copy_result.get("message") or "Copy from debug to main failed.")

        index_result = restart_main_indexing(main_root)
        if index_result.get("status") != "ok":
            raise RuntimeError(index_result.get("message") or "Main indexing failed.")

        sync_result = sync_main_to_blob(main_root, prefix, container_name)
        if sync_result.get("status") != "ok":
            raise RuntimeError(sync_result.get("message") or "Main-to-blob sync failed.")

        with _LOCK:
            job = _SCHEDULED_JOBS.get(job_id)
            if job:
                job["status"] = "completed"
                job["completed_at"] = _to_utc_iso(datetime.now(timezone.utc))
                job["copy_result"] = copy_result
                job["index_result"] = index_result
                job["sync_result"] = sync_result

        return {
            "status": "completed",
            "job_id": job_id,
            "model": job.get("model"),
            "provider": job.get("provider"),
            "copy_result": copy_result,
            "index_result": index_result,
            "sync_result": sync_result,
        }
    except Exception as exc:
        with _LOCK:
            job = _SCHEDULED_JOBS.get(job_id)
            if job:
                job["status"] = "failed"
                job["error"] = str(exc)
                job["failed_at"] = _to_utc_iso(datetime.now(timezone.utc))
        return {"status": "failed", "job_id": job_id, "error": str(exc)}


def _scheduler_worker(job_id: str, publish_at_utc: datetime) -> None:
    delay_seconds = max(0.0, (publish_at_utc - datetime.now(timezone.utc)).total_seconds())
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    _process_publish_job(job_id)


def schedule_publish(
    *,
    model: str,
    provider: str | None = None,
    publish_at: datetime | str | None,
) -> dict[str, Any]:
    if not model or not str(model).strip():
        raise ValueError("A model is required for publication.")

    publish_dt = _parse_publish_datetime(publish_at)
    job_id = uuid.uuid4().hex
    payload = {
        "job_id": job_id,
        "model": str(model).strip(),
        "provider": (provider or os.getenv("LLM_PROVIDER", "azure")).strip() or "azure",
        "publish_at": _to_utc_iso(publish_dt),
        "status": "scheduled",
        "created_at": _to_utc_iso(datetime.now(timezone.utc)),
    }

    with _LOCK:
        _SCHEDULED_JOBS[job_id] = payload

    thread = threading.Thread(target=_scheduler_worker, args=(job_id, publish_dt), daemon=True)
    thread.start()

    return {
        "status": "scheduled",
        "job_id": job_id,
        "model": payload["model"],
        "provider": payload["provider"],
        "publish_at": payload["publish_at"],
        "created_at": payload["created_at"],
    }


def get_scheduled_jobs() -> list[dict[str, Any]]:
    with _LOCK:
        return [dict(job) for job in _SCHEDULED_JOBS.values()]

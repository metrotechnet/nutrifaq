"""Service helpers for third-party API ingestion flows."""

import hmac
import os
from pathlib import Path

from fastapi import Header, HTTPException

from api.services.blob_storage_service import (
    get_blob_prefix,
    has_blob_storage_config,
    upload_file_to_blob,
)
from api.services.config import DBASE_MAIN_TARGET_ROOT


def azure_sync_is_enabled() -> bool:
    """Return True only when Azure sync has been explicitly enabled for this environment."""
    for env_name in (
        "NUTRIFAQ_ENABLE_AZURE_SYNC",
        "ENABLE_LOCAL_DEBUG_AZURE_SYNC",
        "ENABLE_AZURE_SYNC",
    ):
        raw_value = (os.getenv(env_name) or "").strip().lower()
        if not raw_value:
            continue
        if raw_value in {"1", "true", "yes", "on"}:
            return True
        if raw_value in {"0", "false", "no", "off"}:
            return False
    return False


def require_transfer_key(x_client_key: str | None = Header(default=None, alias="X-Client-Key")) -> None:
    expected_key = os.getenv("QUERY_ACCESS_KEY", "").strip()
    provided_key = (x_client_key or "").strip()

    if not expected_key:
        raise HTTPException(status_code=500, detail="Server transfer key is not configured.")
    if not provided_key or not hmac.compare_digest(provided_key, expected_key):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Client-Key.")


def documents_dir() -> Path:
    docs_dir = DBASE_MAIN_TARGET_ROOT / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    return docs_dir


def _safe_filename(filename: str) -> str:
    name = Path(filename or "").name.strip()
    return name or "uploaded-file"


def _azure_blob_path_for_document(filename: str) -> str:
    prefix = get_blob_prefix().strip("/")
    relative_path = f"documents/{_safe_filename(filename)}".strip("/")
    return f"{prefix}/{relative_path}" if prefix else relative_path


def save_uploaded_file(filename: str, content: bytes) -> dict[str, str | bool]:
    docs_dir = documents_dir()

    final_filename = _safe_filename(filename)
    destination = docs_dir / final_filename
    destination.write_bytes(content)

    result: dict[str, str | bool] = {
        "status": "saved",
        "filename": final_filename,
        "path": str(destination.relative_to(DBASE_MAIN_TARGET_ROOT.parent)).replace("\\", "/"),
        "azure_synced": False,
    }

    if not has_blob_storage_config() or not azure_sync_is_enabled():
        return result

    try:
        blob_name = _azure_blob_path_for_document(final_filename)
        upload_file_to_blob(blob_name, destination, overwrite=True)
        result["azure_synced"] = True
        result["azure_blob_path"] = blob_name
    except Exception as exc:
        result["azure_synced"] = False
        result["azure_sync_error"] = str(exc)

    return result


def list_uploaded_files() -> dict[str, object]:
    docs_dir = documents_dir()

    files: list[dict[str, object]] = []
    for path in sorted(docs_dir.glob("*")):
        if not path.is_file():
            continue

        stat = path.stat()
        files.append(
            {
                "filename": path.name,
                "size": stat.st_size,
                "last_modified": stat.st_mtime,
            }
        )

    return {
        "status": "ok",
        "count": len(files),
        "files": files,
    }


def delete_uploaded_file(filename: str) -> dict[str, str]:
    docs_dir = documents_dir()

    final_filename = _safe_filename(filename)
    destination = docs_dir / final_filename
    if not destination.exists() or not destination.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    destination.unlink()
    return {
        "status": "deleted",
        "filename": final_filename,
    }
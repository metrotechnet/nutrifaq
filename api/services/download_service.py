"""Service helpers for third-party API ingestion flows."""

import hmac
import os
from pathlib import Path

from fastapi import Header, HTTPException

from api.services.config import DBASE_MAIN_TARGET_ROOT


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


def save_uploaded_file(filename: str, content: bytes) -> dict[str, str]:
    docs_dir = documents_dir()

    final_filename = _safe_filename(filename)
    destination = docs_dir / final_filename
    destination.write_bytes(content)

    return {
        "status": "saved",
        "filename": final_filename,
        "path": str(destination.relative_to(DBASE_MAIN_TARGET_ROOT.parent)).replace("\\", "/"),
    }


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
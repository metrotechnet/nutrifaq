"""Blob container management routes."""

from __future__ import annotations

import os
from dataclasses import asdict
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from api.services.entra_auth_service import require_admin, require_collaborator

from api.services.blob_storage_service import (
    delete_blob,
    get_blob_prefix,
    get_blob_container_name,
    get_container_client,
    list_blob_files,
    upload_file_to_blob,
)


router = APIRouter()


def _documents_prefix() -> str:
    return f"{get_blob_prefix().strip('/')}/documents/"


def _normalize_requested_prefix(prefix: str) -> str:
    """Normalize optional user prefix and tolerate container-qualified notation."""
    raw = prefix.strip().lstrip("/")
    if not raw:
        return ""

    container_prefix = f"{get_blob_container_name().strip('/')}/"
    if raw.lower().startswith(container_prefix.lower()):
        raw = raw[len(container_prefix):]

    return raw


def _resolve_upload_target(blob_name: str) -> str:
    """Force uploads into the documents subtree regardless of provided path."""
    normalized = _normalize_requested_prefix(blob_name)
    base_prefix = _documents_prefix()

    if normalized.lower().startswith(base_prefix.lower()):
        candidate = normalized
    else:
        leaf = normalized.split("/")[-1] if normalized else ""
        candidate = f"{base_prefix}{leaf}" if leaf else base_prefix

    # Ensure no trailing separator and no empty target file name.
    candidate = candidate.rstrip("/")
    if candidate.lower() == base_prefix.rstrip("/").lower():
        raise HTTPException(status_code=400, detail="Invalid target file name for upload.")
    return candidate


@router.get("/api/blob/files")
def list_files(
    prefix: str | None = Query(default=None, description="Optional blob prefix filter."),
    _: object = Depends(require_collaborator),
):
    """List files currently stored in the Azure blob container."""
    base_prefix = _documents_prefix()
    user_prefix = _normalize_requested_prefix(prefix or "")

    # Keep listing constrained to the documents subtree.
    if user_prefix and user_prefix.lower().startswith(base_prefix.lower()):
        effective_prefix = user_prefix
    elif user_prefix:
        effective_prefix = f"{base_prefix}{user_prefix}"
    else:
        effective_prefix = base_prefix

    files = list_blob_files(prefix=effective_prefix)
    return {
        "status": "ok",
        "container": get_blob_container_name(),
        "prefix": effective_prefix,
        "count": len(files),
        "files": [asdict(file) for file in files],
    }


@router.get("/api/blob/files/{blob_name:path}/download")
def download_file(blob_name: str, _: object = Depends(require_collaborator)):
    """Download a blob as a streamed response."""
    try:
        blob_client = get_container_client().get_blob_client(blob_name)
        stream = blob_client.download_blob()
        return StreamingResponse(
            BytesIO(stream.readall()),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{blob_name.split("/")[-1]}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/blob/files/{blob_name:path}")
async def upload_file(blob_name: str, file: UploadFile = File(...), _: object = Depends(require_admin)):
    """Upload a file into the Azure blob container."""
    try:
        target_blob_name = _resolve_upload_target(blob_name)
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(await file.read())
            temp_path = temp_file.name

        try:
            upload_file_to_blob(target_blob_name, source_path=Path(temp_path), overwrite=True)
        finally:
            os.unlink(temp_path)

        return {"status": "ok", "blob_name": target_blob_name, "filename": file.filename}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/api/blob/files/{blob_name:path}")
def remove_file(blob_name: str, _: object = Depends(require_admin)):
    """Delete a blob from the Azure container."""
    try:
        delete_blob(blob_name)
        return JSONResponse(status_code=200, content={"status": "ok", "blob_name": blob_name})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

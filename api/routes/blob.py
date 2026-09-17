"""Blob container management routes."""

from __future__ import annotations

import os
from dataclasses import asdict
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from api.services.blob_storage_service import (
    delete_blob,
    get_blob_container_name,
    get_container_client,
    list_blob_files,
    upload_file_to_blob,
)


router = APIRouter()


@router.get("/api/blob/files")
def list_files(prefix: str | None = Query(default=None, description="Optional blob prefix filter.")):
    """List files currently stored in the Azure blob container."""
    files = list_blob_files(prefix=prefix)
    return {
        "status": "ok",
        "container": get_blob_container_name(),
        "count": len(files),
        "files": [asdict(file) for file in files],
    }


@router.get("/api/blob/files/{blob_name:path}/download")
def download_file(blob_name: str):
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
async def upload_file(blob_name: str, file: UploadFile = File(...)):
    """Upload a file into the Azure blob container."""
    try:
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(await file.read())
            temp_path = temp_file.name

        try:
            upload_file_to_blob(blob_name, source_path=Path(temp_path), overwrite=True)
        finally:
            os.unlink(temp_path)

        return {"status": "ok", "blob_name": blob_name, "filename": file.filename}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/api/blob/files/{blob_name:path}")
def remove_file(blob_name: str):
    """Delete a blob from the Azure container."""
    try:
        delete_blob(blob_name)
        return JSONResponse(status_code=200, content={"status": "ok", "blob_name": blob_name})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

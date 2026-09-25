"""Blob container management routes."""

from __future__ import annotations

import os
from dataclasses import asdict
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from api.services.entra_auth_service import require_admin, require_collaborator
from api.schemas.models import BlobContainerCopyRequest
from api.services.query_chromadb import get_debug_local_kb_root_folder

from api.services.blob_storage_service import (
    copy_blobs_between_containers,
    delete_blob,
    get_blob_prefix,
    get_blob_container_name,
    get_container_client,
    list_blob_files,
    sync_local_directory_to_blob,
    sync_blob_prefix_to_local,
    upload_file_to_blob,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


router = APIRouter()


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _documents_prefix(root_folder: str | None = None) -> str:
    base_root = (root_folder or get_blob_prefix()).strip("/")
    return f"{base_root}/documents/"


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _debug_local_root(root_folder: str | None = None) -> Path:
    resolved_root = (root_folder or get_debug_local_kb_root_folder()).strip("/")
    return REPO_ROOT / resolved_root


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _strip_known_root_prefix(path_value: str, root_folder: str | None = None) -> str:
    raw = (path_value or "").strip().lstrip("/")
    if not raw:
        return ""

    known_root = (root_folder or get_debug_local_kb_root_folder()).strip("/")
    variants = [
        f"{known_root}/",
        f"{known_root}",
        "nutrifaq-dbase-main/",
        "nutrifaq-dbase-main",
        "nutrifaq-dbase-prod/",
        "nutrifaq-dbase-prod",
    ]
    for variant in variants:
        if raw.lower().startswith(variant.lower()):
            raw = raw[len(variant):].lstrip("/")
            break

    if raw.lower().startswith("documents/") or raw.lower() == "documents":
        return raw.strip("/")
    return raw.strip("/")


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _local_file_path(blob_name: str, root_folder: str | None = None) -> Path:
    relative_name = _strip_known_root_prefix(blob_name, root_folder=root_folder)
    if not relative_name:
        raise HTTPException(status_code=400, detail="Invalid local file path for debug KB.")
    return _debug_local_root(root_folder) / relative_name


def _related_transcript_paths(document_path: Path, root_folder: str | None = None) -> list[Path]:
    """Return transcript files that correspond to a document path under documents/."""
    local_root = _debug_local_root(root_folder)
    documents_root = local_root / "documents"
    transcripts_root = local_root / "transcripts"
    if not transcripts_root.exists():
        return []

    try:
        relative_doc = document_path.relative_to(documents_root)
    except ValueError:
        return []

    candidates = [
        transcripts_root / relative_doc.with_suffix(".txt"),
        transcripts_root / f"{relative_doc.stem}.txt",
    ]

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique_candidates.append(candidate)

    return unique_candidates


def _normalize_requested_prefix(prefix: str, container_name: str | None = None) -> str:
    """Normalize optional user prefix and tolerate container-qualified notation."""
    raw = prefix.strip().lstrip("/")
    if not raw:
        return ""

    container_prefix = f"{get_blob_container_name(container_name).strip('/')}/"
    if raw.lower().startswith(container_prefix.lower()):
        raw = raw[len(container_prefix):]

    return raw


def _resolve_upload_target(blob_name: str, root_folder: str | None = None) -> str:
    """Force uploads into the debug KB local documents subtree regardless of provided path."""
    normalized = _strip_known_root_prefix(blob_name, root_folder=root_folder)
    if not normalized:
        raise HTTPException(status_code=400, detail="Invalid target file name for upload.")

    if normalized.lower().startswith("documents/") or normalized.lower() == "documents":
        candidate = normalized
    else:
        leaf = normalized.split("/")[-1] if normalized else ""
        candidate = f"documents/{leaf}" if leaf else "documents"

    candidate = candidate.strip("/")
    if not candidate or candidate.lower() == "documents":
        raise HTTPException(status_code=400, detail="Invalid target file name for upload.")
    return candidate


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _list_local_debug_files(prefix: str | None = None, root_folder: str | None = None) -> list[dict]:
    local_root = _debug_local_root(root_folder)
    documents_root = local_root / "documents"
    if not documents_root.exists():
        return []

    normalized_prefix = (_strip_known_root_prefix(prefix or "", root_folder=root_folder)).strip("/")
    if normalized_prefix.lower().startswith("documents/"):
        requested_prefix = normalized_prefix[len("documents/"):].strip("/")
    elif normalized_prefix.lower() == "documents":
        requested_prefix = ""
    else:
        requested_prefix = normalized_prefix

    files: list[dict] = []
    for path in sorted(documents_root.rglob("*")):
        if not path.is_file():
            continue

        relative_name = path.relative_to(documents_root).as_posix()
        if requested_prefix and not relative_name.startswith(requested_prefix):
            continue

        files.append(
            {
                "name": f"{(root_folder or get_debug_local_kb_root_folder()).strip('/')}/documents/{relative_name}",
                "size": path.stat().st_size,
                "etag": None,
                "last_modified": path.stat().st_mtime,
                "content_type": None,
            }
        )

    return files


@router.get("/api/blob/files")
def list_files(
    prefix: str | None = Query(default=None, description="Optional blob prefix filter."),
    container: str | None = Query(default=None, description="Optional blob container name override."),
    root_folder: str | None = Query(default=None, description="Optional blob root folder override."),
    _: object = Depends(require_collaborator),
):
    """List files from the local debug KB working directory."""
    resolved_root = (root_folder or get_debug_local_kb_root_folder()).strip("/")
    local_files = _list_local_debug_files(prefix or "", root_folder=root_folder)
    effective_prefix = _strip_known_root_prefix(prefix or "", root_folder=root_folder)
    effective_prefix = effective_prefix.strip("/")
    return {
        "status": "ok",
        "container": get_blob_container_name(container),
        "prefix": effective_prefix or resolved_root,
        "count": len(local_files),
        "files": local_files,
    }


@router.get("/api/blob/files/{blob_name:path}/download")
def download_file(
    blob_name: str,
    container: str | None = Query(default=None, description="Optional blob container name override."),
    _: object = Depends(require_collaborator),
):
    """Download a file from the local debug KB working directory."""
    try:
        local_path = _local_file_path(blob_name)
        if not local_path.exists() or not local_path.is_file():
            raise FileNotFoundError(f"File not found: {blob_name}")

        return StreamingResponse(
            local_path.open("rb"),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{local_path.name}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/blob/files/{blob_name:path}")
async def upload_file(
    blob_name: str,
    file: UploadFile = File(...),
    container: str | None = Query(default=None, description="Optional blob container name override."),
    root_folder: str | None = Query(default=None, description="Optional blob root folder override."),
    _: object = Depends(require_admin),
):
    """Upload a file into the local debug KB working directory."""
    try:
        target_relative_name = _resolve_upload_target(blob_name, root_folder)
        target_path = _debug_local_root(root_folder) / target_relative_name
        target_path.parent.mkdir(parents=True, exist_ok=True)

        content = await file.read()
        with open(target_path, "wb") as target_file:
            target_file.write(content)

        return {"status": "ok", "blob_name": target_relative_name, "filename": file.filename}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/api/blob/files/{blob_name:path}")
def remove_file(
    blob_name: str,
    container: str | None = Query(default=None, description="Optional blob container name override."),
    _: object = Depends(require_admin),
):
    """Delete a file from the local debug KB working directory."""
    try:
        target_path = _local_file_path(blob_name)
        if not target_path.exists():
            raise FileNotFoundError(f"File not found: {blob_name}")

        removed_files: list[str] = []

        transcript_paths = _related_transcript_paths(target_path)
        target_path.unlink()
        removed_files.append(str(target_path))

        for transcript_path in transcript_paths:
            if transcript_path.exists() and transcript_path.is_file():
                transcript_path.unlink()
                removed_files.append(str(transcript_path))

        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "blob_name": blob_name,
                "removed_files": removed_files,
            },
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/blob/copy-container")
def copy_container_files(
    copy_request: BlobContainerCopyRequest,
    _: object = Depends(require_admin),
):
    """Copy blobs from a source container to a destination container."""
    try:
        effective_overwrite = True
        return {
            "status": "ok",
            "result": copy_blobs_between_containers(
                source_container=copy_request.source_container,
                destination_container=copy_request.destination_container,
                source_prefix=copy_request.source_prefix,
                destination_prefix=copy_request.destination_prefix,
                overwrite=effective_overwrite,
                wait_for_completion=copy_request.wait_for_completion,
                timeout_seconds=copy_request.timeout_seconds,
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/blob/debug/reset-local")
def reset_local_debug_from_blob(
    container: str | None = Query(default=None, description="Optional blob container name override."),
    root_folder: str | None = Query(default=None, description="Optional blob root folder override."),
    _: object = Depends(require_admin),
):
    """Reset local debug KB files by syncing the debug prefix from blob to local."""
    try:
        resolved_root = (root_folder or get_debug_local_kb_root_folder()).strip("/")
        resolved_container = get_blob_container_name(container)
        local_root = _debug_local_root(root_folder)
        synced_path = sync_blob_prefix_to_local(
            resolved_root,
            local_root,
            remove_existing=True,
            container_name=resolved_container,
        )

        local_files = _list_local_debug_files(_documents_prefix(resolved_root), root_folder=resolved_root)
        return {
            "status": "ok",
            "container": resolved_container,
            "root_folder": resolved_root,
            "local_path": str(synced_path),
            "documents_count": len(local_files),
            "message": "Debug files synced from blob to local.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/blob/debug/sync-local-to-blob")
def sync_local_debug_to_blob(
    container: str | None = Query(default=None, description="Optional blob container name override."),
    root_folder: str | None = Query(default=None, description="Optional blob root folder override."),
    _: object = Depends(require_admin),
):
    """Sync local debug KB files to blob and wait for completion before returning."""
    try:
        resolved_root = (root_folder or get_debug_local_kb_root_folder()).strip("/")
        resolved_container = get_blob_container_name(container)
        local_root = _debug_local_root(root_folder)

        if not local_root.exists() or not local_root.is_dir():
            raise HTTPException(status_code=404, detail=f"Debug local root not found: {local_root}")

        uploaded = sync_local_directory_to_blob(
            local_root,
            resolved_root,
            overwrite=True,
            container_name=resolved_container,
        )

        return {
            "status": "ok",
            "container": resolved_container,
            "root_folder": resolved_root,
            "local_path": str(local_root),
            "uploaded_files_count": len(uploaded),
            "uploaded_files": uploaded,
            "message": "Debug local files synced to blob.",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

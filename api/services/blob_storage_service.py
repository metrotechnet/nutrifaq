"""Azure Blob Storage helpers for NutriFAQ knowledge-base files."""

from __future__ import annotations

import os
import shutil
import mimetypes
import time
import logging
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

try:
    from azure.storage.blob import BlobServiceClient
except ImportError:  # pragma: no cover - optional in local/test environments
    BlobServiceClient = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_BLOB_UPLOAD_QUEUE_MAX_SIZE = max(1, int(os.getenv("BLOB_UPLOAD_QUEUE_MAX_SIZE", "1024")))
_BLOB_UPLOAD_QUEUE: queue.Queue[tuple[str, str, bool, str | None]] = queue.Queue(maxsize=_BLOB_UPLOAD_QUEUE_MAX_SIZE)
_BLOB_UPLOAD_WORKER_LOCK = threading.Lock()
_BLOB_UPLOAD_WORKER: threading.Thread | None = None


@dataclass(frozen=True)
class BlobFileInfo:
    name: str
    size: int | None
    etag: str | None
    last_modified: str | None
    content_type: str | None


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _storage_connection_string() -> str | None:
    return os.getenv("AZURE_STORAGE_CONNECTION_STRING")


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _storage_account_name() -> str | None:
    return os.getenv("AZURE_STORAGE_ACCOUNT")


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _storage_account_key() -> str | None:
    return os.getenv("AZURE_STORAGE_KEY")


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _storage_sas_token() -> str | None:
    return os.getenv("AZURE_STORAGE_SAS_TOKEN")


# Purpose: Implement a focused unit of backend behavior used by routes or services.
# Inputs/Outputs: See signature and return annotation for contract details.
def has_blob_storage_config() -> bool:
    return bool(_storage_connection_string() or (_storage_account_name() and _storage_account_key()))


# Purpose: Retrieve data needed by callers and return it in a ready-to-use format.
# Inputs/Outputs: See signature and return annotation for contract details.
def get_blob_container_name(container_name: str | None = None) -> str:
    if container_name:
        return container_name

    # Default to the debug container for KB operations so the admin UI and file actions
    # stay aligned with the debug dataset unless an explicit override is passed.
    return os.getenv(
        "AZURE_KB_DEBUG_BLOB_CONTAINER",
        os.getenv("AZURE_STORAGE_CONTAINER", os.getenv("AZURE_KB_BLOB_CONTAINER", "nutrifaq-dbase-main")),
    )


# Purpose: Retrieve data needed by callers and return it in a ready-to-use format.
# Inputs/Outputs: See signature and return annotation for contract details.
def get_blob_prefix() -> str:
    return os.getenv(
        "AZURE_KB_DEBUG_BLOB_PREFIX",
        os.getenv("AZURE_KB_BLOB_PREFIX", "nutrifaq-dbase-main"),
    ).strip("/")


# Purpose: Retrieve data needed by callers and return it in a ready-to-use format.
# Inputs/Outputs: See signature and return annotation for contract details.
def get_blob_service_client() -> Any:
    if BlobServiceClient is None:
        raise RuntimeError("azure-storage-blob is not installed in the current environment.")

    connection_string = _storage_connection_string()
    if connection_string:
        return BlobServiceClient.from_connection_string(connection_string)

    account_name = _storage_account_name()
    account_key = _storage_account_key()
    if account_name and account_key:
        account_url = f"https://{account_name}.blob.core.windows.net"
        credential = _storage_sas_token() or account_key
        return BlobServiceClient(account_url=account_url, credential=credential)

    raise RuntimeError("Azure Blob Storage configuration is required.")


# Purpose: Retrieve data needed by callers and return it in a ready-to-use format.
# Inputs/Outputs: See signature and return annotation for contract details.
def get_container_client(container_name: str | None = None):
    client = get_blob_service_client()
    return client.get_container_client(get_blob_container_name(container_name))


# Purpose: Collect and return a list view for API responses or internal processing.
# Inputs/Outputs: See signature and return annotation for contract details.
def list_blob_files(prefix: str | None = None, container_name: str | None = None) -> list[BlobFileInfo]:
    container_client = get_container_client(container_name)
    blobs = container_client.list_blobs(name_starts_with=prefix)
    return [
        BlobFileInfo(
            name=blob.name,
            size=getattr(blob, "size", None),
            etag=getattr(blob, "etag", None),
            last_modified=str(getattr(blob, "last_modified", None)) if getattr(blob, "last_modified", None) else None,
            content_type=(
                getattr(getattr(blob, "content_settings", None), "content_type", None)
                or mimetypes.guess_type(blob.name)[0]
            ),
        )
        for blob in blobs
    ]


# Purpose: Retrieve data needed by callers and return it in a ready-to-use format.
# Inputs/Outputs: See signature and return annotation for contract details.
def get_blob_properties(blob_name: str, container_name: str | None = None):
    return get_container_client(container_name).get_blob_client(blob_name).get_blob_properties()


# Purpose: Implement a focused unit of backend behavior used by routes or services.
# Inputs/Outputs: See signature and return annotation for contract details.
def download_blob_to_path(blob_name: str, destination_path: Path, container_name: str | None = None) -> Path:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    blob_client = get_container_client(container_name).get_blob_client(blob_name)
    with open(destination_path, "wb") as target_file:
        target_file.write(blob_client.download_blob().readall())
    return destination_path


# Purpose: Implement a focused unit of backend behavior used by routes or services.
# Inputs/Outputs: See signature and return annotation for contract details.
def upload_file_to_blob(
    blob_name: str,
    source_path: Path,
    overwrite: bool = True,
    container_name: str | None = None,
) -> str:
    normalized_blob_name = str(blob_name or "").strip()
    if not normalized_blob_name:
        raise ValueError("blob_name is required.")
    _enqueue_blob_upload(
        blob_name=normalized_blob_name,
        source_path=Path(source_path),
        overwrite=overwrite,
        container_name=container_name,
    )
    return normalized_blob_name


def _ensure_blob_upload_worker() -> None:
    global _BLOB_UPLOAD_WORKER
    with _BLOB_UPLOAD_WORKER_LOCK:
        if _BLOB_UPLOAD_WORKER is not None and _BLOB_UPLOAD_WORKER.is_alive():
            return

        worker = threading.Thread(
            target=_blob_upload_worker_loop,
            name="blob-upload-worker",
            daemon=True,
        )
        worker.start()
        _BLOB_UPLOAD_WORKER = worker


def _enqueue_blob_upload(
    *,
    blob_name: str,
    source_path: Path,
    overwrite: bool,
    container_name: str | None,
) -> None:
    _ensure_blob_upload_worker()
    payload = (blob_name, str(source_path), bool(overwrite), container_name)
    try:
        _BLOB_UPLOAD_QUEUE.put_nowait(payload)
    except queue.Full:
        try:
            _BLOB_UPLOAD_QUEUE.get_nowait()
            _BLOB_UPLOAD_QUEUE.task_done()
        except queue.Empty:
            pass
        try:
            _BLOB_UPLOAD_QUEUE.put_nowait(payload)
        except queue.Full:
            logger.warning("Blob upload queue is full; dropping upload for '%s'.", blob_name)


def _blob_upload_worker_loop() -> None:
    while True:
        blob_name, source_path_text, overwrite, container_name = _BLOB_UPLOAD_QUEUE.get()
        try:
            _upload_file_to_blob_blocking(
                blob_name=blob_name,
                source_path=Path(source_path_text),
                overwrite=overwrite,
                container_name=container_name,
            )
        except Exception as exc:
            logger.warning(
                "Async blob upload failed for '%s' from '%s': %s",
                blob_name,
                source_path_text,
                exc,
            )
        finally:
            _BLOB_UPLOAD_QUEUE.task_done()


def _upload_file_to_blob_blocking(
    *,
    blob_name: str,
    source_path: Path,
    overwrite: bool,
    container_name: str | None,
) -> str:
    blob_client = get_container_client(container_name).get_blob_client(blob_name)
    max_retries = max(0, int(os.getenv("BLOB_FILE_LOCK_RETRIES", "12")))
    base_delay_seconds = max(0.05, float(os.getenv("BLOB_FILE_LOCK_RETRY_BASE_SECONDS", "0.15")))
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            with open(source_path, "rb") as source_file:
                blob_client.upload_blob(source_file, overwrite=overwrite)
            return blob_name
        except PermissionError as exc:
            last_error = exc
        except OSError as exc:
            if getattr(exc, "winerror", None) != 32:
                raise
            last_error = exc

        if attempt >= max_retries:
            break

        delay = base_delay_seconds * (attempt + 1)
        logger.warning(
            "File is locked during blob upload, retrying in %.2fs (%s/%s): %s",
            delay,
            attempt + 1,
            max_retries,
            source_path,
        )
        time.sleep(delay)

    raise RuntimeError(
        f"Unable to upload locked file '{source_path}' to blob '{blob_name}' after {max_retries + 1} attempts."
    ) from last_error


# Purpose: Delete the targeted resource and keep state consistent after removal.
# Inputs/Outputs: See signature and return annotation for contract details.
def delete_blob(blob_name: str, container_name: str | None = None) -> None:
    get_container_client(container_name).delete_blob(blob_name)


# Purpose: Synchronize source and destination data while preserving operational safety.
# Inputs/Outputs: See signature and return annotation for contract details.
def sync_blob_prefix_to_local(
    prefix: str,
    local_root: Path,
    *,
    remove_existing: bool = True,
    container_name: str | None = None,
) -> Path:
    container_client = get_container_client(container_name)
    blobs = list(container_client.list_blobs(name_starts_with=prefix))

    if remove_existing and local_root.exists():
        try:
            shutil.rmtree(local_root)
        except PermissionError:
            # On Windows a Chroma file can be locked by another process; keep the existing cache.
            pass
    local_root.mkdir(parents=True, exist_ok=True)

    for blob in blobs:
        if blob.name.endswith("/"):
            continue

        relative_path = blob.name[len(prefix):].lstrip("/")
        if not relative_path:
            continue

        target_path = local_root / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            download_blob_to_path(blob.name, target_path, container_name=container_name)
        except PermissionError:
            # Skip locked files and continue hydration best-effort.
            continue

    return local_root


# Purpose: Synchronize source and destination data while preserving operational safety.
# Inputs/Outputs: See signature and return annotation for contract details.
def sync_local_directory_to_blob(
    source_root: Path,
    destination_prefix: str,
    *,
    overwrite: bool = True,
    clear_destination_first: bool = True,
    container_name: str | None = None,
    is_cancel_requested: Callable[[], bool] | None = None,
    on_file_transferred: Callable[[dict[str, Any]], None] | None = None,
) -> list[str]:
    uploaded: list[str] = []
    prefix_clean = (destination_prefix or "").strip().strip("/")
    if clear_destination_first:
        container_client = get_container_client(container_name)
        list_prefix = f"{prefix_clean}/" if prefix_clean else None
        for blob in container_client.list_blobs(name_starts_with=list_prefix):
            if callable(is_cancel_requested) and is_cancel_requested():
                raise RuntimeError("Operation cancelled by user.")
            container_client.delete_blob(blob.name)
    files = [path for path in source_root.rglob("*") if path.is_file()]
    total_files = len(files)
    for index, path in enumerate(files, start=1):
        if callable(is_cancel_requested) and is_cancel_requested():
            raise RuntimeError("Operation cancelled by user.")
        relative = path.relative_to(source_root).as_posix()
        blob_name = f"{prefix_clean}/{relative}" if prefix_clean else relative
        _upload_file_to_blob_blocking(
            blob_name=blob_name,
            source_path=path,
            overwrite=overwrite,
            container_name=container_name,
        )
        uploaded.append(blob_name)
        if callable(on_file_transferred):
            on_file_transferred(
                {
                    "index": index,
                    "total": total_files,
                    "source_path": str(path),
                    "blob_name": blob_name,
                }
            )
    return uploaded


def copy_blobs_between_containers(
    source_container: str,
    destination_container: str,
    *,
    source_prefix: str | None = None,
    destination_prefix: str | None = None,
    overwrite: bool = True,
    wait_for_completion: bool = True,
    timeout_seconds: int = 120,
    is_cancel_requested: Callable[[], bool] | None = None,
    on_file_transferred: Callable[[dict[str, Any]], None] | None = None,
) -> dict:
    """Copy blobs from one container to another, optionally scoped by prefix."""
    normalized_source = (source_container or "").strip()
    normalized_destination = (destination_container or "").strip()
    if not normalized_source or not normalized_destination:
        raise ValueError("Both source_container and destination_container are required.")
    if normalized_source == normalized_destination and not source_prefix and not destination_prefix:
        raise ValueError("Source and destination are identical. Provide prefixes or different containers.")

    source_prefix_clean = (source_prefix or "").strip().strip("/")
    destination_prefix_clean = (destination_prefix or "").strip().strip("/")
    source_prefix_with_sep = f"{source_prefix_clean}/" if source_prefix_clean else ""

    source_client = get_container_client(normalized_source)
    destination_client = get_container_client(normalized_destination)

    blobs_to_copy: list[str] = []
    for blob in source_client.list_blobs(name_starts_with=source_prefix_with_sep or None):
        source_blob_name = blob.name
        if source_blob_name.endswith("/"):
            continue
        relative_name = source_blob_name
        if source_prefix_with_sep and source_blob_name.startswith(source_prefix_with_sep):
            relative_name = source_blob_name[len(source_prefix_with_sep):]
        if not relative_name:
            continue
        blobs_to_copy.append(source_blob_name)

    total_blobs = len(blobs_to_copy)
    copied: list[dict] = []
    skipped: list[dict] = []
    failed: list[dict] = []

    cancelled = False

    for source_blob_name in blobs_to_copy:
        if callable(is_cancel_requested) and is_cancel_requested():
            cancelled = True
            break

        relative_name = source_blob_name
        if source_prefix_with_sep and source_blob_name.startswith(source_prefix_with_sep):
            relative_name = source_blob_name[len(source_prefix_with_sep):]

        if not relative_name:
            continue

        destination_blob_name = (
            f"{destination_prefix_clean}/{relative_name}" if destination_prefix_clean else relative_name
        )
        destination_blob = destination_client.get_blob_client(destination_blob_name)
        destination_exists = destination_blob.exists()

        if destination_exists and not overwrite:
            skipped.append({"source": source_blob_name, "destination": destination_blob_name, "reason": "exists"})
            continue

        if destination_exists and overwrite:
            destination_blob.delete_blob(delete_snapshots="include")

        source_blob = source_client.get_blob_client(source_blob_name)
        copy_result = destination_blob.start_copy_from_url(source_blob.url)
        copy_id = copy_result.get("copy_id") if isinstance(copy_result, dict) else None

        if wait_for_completion:
            deadline = time.monotonic() + max(timeout_seconds, 1)
            last_status = "pending"

            while time.monotonic() < deadline:
                if callable(is_cancel_requested) and is_cancel_requested():
                    cancelled = True
                    if copy_id:
                        try:
                            destination_blob.abort_copy(copy_id)
                        except Exception:
                            pass
                    break
                props = destination_blob.get_blob_properties()
                copy_props = getattr(props, "copy", None)
                status = getattr(copy_props, "status", None) or "success"
                last_status = status.lower()
                if last_status in {"success", "failed", "aborted"}:
                    break
                time.sleep(0.2)

            if cancelled:
                break

            if last_status != "success":
                failed.append(
                    {
                        "source": source_blob_name,
                        "destination": destination_blob_name,
                        "copy_id": copy_id,
                        "status": last_status,
                    }
                )
                continue

        copied.append(
            {
                "source": source_blob_name,
                "destination": destination_blob_name,
                "copy_id": copy_id,
            }
        )
        if callable(on_file_transferred):
            on_file_transferred(
                {
                    "index": len(copied),
                    "total": total_blobs,
                    "source_blob_name": source_blob_name,
                    "destination_blob_name": destination_blob_name,
                }
            )



    return {
        "source_container": normalized_source,
        "destination_container": normalized_destination,
        "source_prefix": source_prefix_clean or None,
        "destination_prefix": destination_prefix_clean or None,
        "overwrite": overwrite,
        "wait_for_completion": wait_for_completion,
        "cancelled": cancelled,
        "copied_count": len(copied),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "copied": copied,
        "skipped": skipped,
        "failed": failed,
    }

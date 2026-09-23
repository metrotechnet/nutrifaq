"""Azure Blob Storage helpers for NutriFAQ knowledge-base files."""

from __future__ import annotations

import os
import shutil
import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    from azure.storage.blob import BlobServiceClient
except ImportError:  # pragma: no cover - optional in local/test environments
    BlobServiceClient = None  # type: ignore[assignment]


@dataclass(frozen=True)
class BlobFileInfo:
    name: str
    size: int | None
    etag: str | None
    last_modified: str | None
    content_type: str | None


def _storage_connection_string() -> str | None:
    return os.getenv("AZURE_STORAGE_CONNECTION_STRING")


def _storage_account_name() -> str | None:
    return os.getenv("AZURE_STORAGE_ACCOUNT")


def _storage_account_key() -> str | None:
    return os.getenv("AZURE_STORAGE_KEY")


def _storage_sas_token() -> str | None:
    return os.getenv("AZURE_STORAGE_SAS_TOKEN")


def has_blob_storage_config() -> bool:
    return bool(_storage_connection_string() or (_storage_account_name() and _storage_account_key()))


def get_blob_container_name(container_name: str | None = None) -> str:
    if container_name:
        return container_name

    # Default to the debug container for KB operations so the admin UI and file actions
    # stay aligned with the debug dataset unless an explicit override is passed.
    return os.getenv(
        "AZURE_KB_DEBUG_BLOB_CONTAINER",
        os.getenv("AZURE_STORAGE_CONTAINER", os.getenv("AZURE_KB_BLOB_CONTAINER", "nutrifaq-knowledge-base-debug")),
    )


def get_blob_prefix() -> str:
    return os.getenv(
        "AZURE_KB_DEBUG_BLOB_PREFIX",
        os.getenv("AZURE_KB_BLOB_PREFIX", "nutrifaq-dbase-main"),
    ).strip("/")


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


def get_container_client(container_name: str | None = None):
    client = get_blob_service_client()
    return client.get_container_client(get_blob_container_name(container_name))


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


def get_blob_properties(blob_name: str, container_name: str | None = None):
    return get_container_client(container_name).get_blob_client(blob_name).get_blob_properties()


def download_blob_to_path(blob_name: str, destination_path: Path, container_name: str | None = None) -> Path:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    blob_client = get_container_client(container_name).get_blob_client(blob_name)
    with open(destination_path, "wb") as target_file:
        target_file.write(blob_client.download_blob().readall())
    return destination_path


def upload_file_to_blob(
    blob_name: str,
    source_path: Path,
    overwrite: bool = True,
    container_name: str | None = None,
) -> str:
    blob_client = get_container_client(container_name).get_blob_client(blob_name)
    with open(source_path, "rb") as source_file:
        blob_client.upload_blob(source_file, overwrite=overwrite)
    return blob_name


def delete_blob(blob_name: str, container_name: str | None = None) -> None:
    get_container_client(container_name).delete_blob(blob_name)


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


def sync_local_directory_to_blob(
    source_root: Path,
    destination_prefix: str,
    *,
    overwrite: bool = True,
    container_name: str | None = None,
) -> list[str]:
    uploaded: list[str] = []
    prefix_clean = (destination_prefix or "").strip().strip("/")
    for path in source_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source_root).as_posix()
        blob_name = f"{prefix_clean}/{relative}" if prefix_clean else relative
        upload_file_to_blob(blob_name, path, overwrite=overwrite, container_name=container_name)
        uploaded.append(blob_name)
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

    copied: list[dict] = []
    skipped: list[dict] = []
    failed: list[dict] = []

    for blob in source_client.list_blobs(name_starts_with=source_prefix_with_sep or None):
        source_blob_name = blob.name
        if source_blob_name.endswith("/"):
            continue

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
                props = destination_blob.get_blob_properties()
                copy_props = getattr(props, "copy", None)
                status = getattr(copy_props, "status", None) or "success"
                last_status = status.lower()
                if last_status in {"success", "failed", "aborted"}:
                    break
                time.sleep(0.2)

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

    return {
        "source_container": normalized_source,
        "destination_container": normalized_destination,
        "source_prefix": source_prefix_clean or None,
        "destination_prefix": destination_prefix_clean or None,
        "overwrite": overwrite,
        "wait_for_completion": wait_for_completion,
        "copied_count": len(copied),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "copied": copied,
        "skipped": skipped,
        "failed": failed,
    }

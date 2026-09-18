"""Azure Blob Storage helpers for NutriFAQ knowledge-base files."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from azure.storage.blob import BlobServiceClient


@dataclass(frozen=True)
class BlobFileInfo:
    name: str
    size: int | None
    etag: str | None
    last_modified: str | None


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


def get_blob_container_name() -> str:
    return os.getenv(
        "AZURE_KB_BLOB_CONTAINER",
        os.getenv("AZURE_STORAGE_CONTAINER", "nutrifaq-knowledge-base"),
    )


def get_blob_prefix() -> str:
    return os.getenv("AZURE_KB_BLOB_PREFIX", "nutrifaq-dbase").strip("/")


def get_blob_service_client() -> BlobServiceClient:
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


def get_container_client():
    client = get_blob_service_client()
    return client.get_container_client(get_blob_container_name())


def list_blob_files(prefix: str | None = None) -> list[BlobFileInfo]:
    container_client = get_container_client()
    blobs = container_client.list_blobs(name_starts_with=prefix)
    return [
        BlobFileInfo(
            name=blob.name,
            size=getattr(blob, "size", None),
            etag=getattr(blob, "etag", None),
            last_modified=str(getattr(blob, "last_modified", None)) if getattr(blob, "last_modified", None) else None,
        )
        for blob in blobs
    ]


def get_blob_properties(blob_name: str):
    return get_container_client().get_blob_client(blob_name).get_blob_properties()


def download_blob_to_path(blob_name: str, destination_path: Path) -> Path:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    blob_client = get_container_client().get_blob_client(blob_name)
    with open(destination_path, "wb") as target_file:
        target_file.write(blob_client.download_blob().readall())
    return destination_path


def upload_file_to_blob(blob_name: str, source_path: Path, overwrite: bool = True) -> str:
    blob_client = get_container_client().get_blob_client(blob_name)
    with open(source_path, "rb") as source_file:
        blob_client.upload_blob(source_file, overwrite=overwrite)
    return blob_name


def delete_blob(blob_name: str) -> None:
    get_container_client().delete_blob(blob_name)


def sync_blob_prefix_to_local(prefix: str, local_root: Path, *, remove_existing: bool = True) -> Path:
    container_client = get_container_client()
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
            download_blob_to_path(blob.name, target_path)
        except PermissionError:
            # Skip locked files and continue hydration best-effort.
            continue

    return local_root


def sync_local_directory_to_blob(source_root: Path, destination_prefix: str, *, overwrite: bool = True) -> list[str]:
    uploaded: list[str] = []
    for path in source_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source_root).as_posix()
        blob_name = f"{destination_prefix.rstrip('/')}/{relative}"
        upload_file_to_blob(blob_name, path, overwrite=overwrite)
        uploaded.append(blob_name)
    return uploaded

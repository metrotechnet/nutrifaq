"""Backup/restore helpers for local auth SQLite database using Azure Blob Storage."""

from __future__ import annotations

import logging
import os
import sqlite3
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from api.services.blob_storage_service import get_container_client, has_blob_storage_config

logger = logging.getLogger(__name__)
_BACKUP_LOCK = threading.Lock()
_BACKUP_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="auth-sqlite-backup")


def _backup_container_name() -> str:
    return (
        os.getenv("AUTH_BACKUP_BLOB_CONTAINER", "").strip()
        or os.getenv("AZURE_STORAGE_CONTAINER", "").strip()
        or "nutrifaq-dbase-main"
    )


def _backup_blob_name() -> str:
    prefix = os.getenv("AUTH_BACKUP_BLOB_PREFIX", "auth-backups").strip().strip("/")
    file_name = os.getenv("AUTH_BACKUP_BLOB_FILE", "auth.sqlite3").strip() or "auth.sqlite3"
    return f"{prefix}/{file_name}" if prefix else file_name


def _backup_enabled() -> bool:
    value = os.getenv("AUTH_SQLITE_BLOB_BACKUP_ENABLED", "1").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _restore_enabled() -> bool:
    value = os.getenv("AUTH_SQLITE_RESTORE_ON_STARTUP", "1").strip().lower()
    return value in {"1", "true", "yes", "on"}


def backup_auth_sqlite_to_blob(sqlite_db_path: Path, reason: str) -> None:
    if not _backup_enabled():
        return
    if not has_blob_storage_config():
        raise RuntimeError("Azure Blob Storage configuration is required for auth SQLite backup.")

    db_path = Path(sqlite_db_path).resolve()
    if not db_path.exists():
        raise RuntimeError(f"Auth SQLite database file not found: {db_path}")

    with _BACKUP_LOCK:
        with tempfile.TemporaryDirectory(prefix="auth-sqlite-backup-") as temp_dir:
            snapshot_path = Path(temp_dir) / "auth.sqlite3"
            source_conn = sqlite3.connect(str(db_path))
            try:
                snapshot_conn = sqlite3.connect(str(snapshot_path))
                try:
                    source_conn.backup(snapshot_conn)
                finally:
                    snapshot_conn.close()
            finally:
                source_conn.close()

            blob_client = get_container_client(_backup_container_name()).get_blob_client(_backup_blob_name())
            with open(snapshot_path, "rb") as stream:
                blob_client.upload_blob(stream, overwrite=True)

    logger.info("Auth SQLite backup uploaded to blob (%s). Reason: %s", _backup_blob_name(), reason)


def backup_auth_sqlite_to_blob_in_background(sqlite_db_path: Path, reason: str) -> None:
    """Schedule auth SQLite backup upload on a background thread."""

    db_path = Path(sqlite_db_path).resolve()

    def _run() -> None:
        try:
            backup_auth_sqlite_to_blob(db_path, reason=reason)
        except Exception:
            logger.exception("Async auth SQLite backup failed. Reason: %s", reason)

    _BACKUP_EXECUTOR.submit(_run)


def restore_auth_sqlite_from_blob(sqlite_db_path: Path) -> bool:
    if not _restore_enabled() or not _backup_enabled():
        return False
    if not has_blob_storage_config():
        return False

    db_path = Path(sqlite_db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with _BACKUP_LOCK:
        blob_client = get_container_client(_backup_container_name()).get_blob_client(_backup_blob_name())
        if not blob_client.exists():
            logger.info("No auth SQLite backup found in blob (%s).", _backup_blob_name())
            return False

        with open(db_path, "wb") as target:
            target.write(blob_client.download_blob().readall())

    logger.info("Auth SQLite database restored from blob backup (%s).", _backup_blob_name())
    return True

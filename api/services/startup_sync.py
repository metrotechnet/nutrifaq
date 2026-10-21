from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from api.services.blob_storage_service import (
    has_blob_storage_config,
    sync_blob_prefix_to_local,
    sync_local_directory_to_blob,
)
from api.services.config import load_prod_config, sync_next_prod_chroma_from_main
from api.services.download_service import azure_sync_is_enabled
from api.services.refusal_engine import load_refusal_patterns, load_refusal_responses

if TYPE_CHECKING:
    from fastapi import FastAPI

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def _load_refusal_config_from_blob() -> None:
    """Load refusal config directly from nutrifaq-config container (no local fallback)."""
    patterns = load_refusal_patterns()
    responses = load_refusal_responses()
    logger.info(
        "[Startup] Loaded refusal config from blob (patterns languages=%s, responses languages=%s).",
        len(patterns),
        len(responses),
    )


def _copy_directory_contents(source: Path, destination: Path) -> None:
    """Copy source directory content into destination directory."""
    if not source.exists():
        raise FileNotFoundError(f"Source directory not found: {source}")

    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def sync_blob_databases_on_startup(app: "FastAPI | None" = None) -> None:
    """Hydrate local folders and prepare prod ChromaDB layout on startup."""
    if app is not None:
        app.state.database_sync_status = "syncing"

    if not azure_sync_is_enabled():
        if app is not None:
            app.state.database_sync_status = "synced"
        logger.info(
            "[Startup] Azure sync is disabled. Set NUTRIFAQ_ENABLE_AZURE_SYNC=true to enable blob/local sync during local debug."
        )
        return

    if not has_blob_storage_config():
        if app is not None:
            app.state.database_sync_status = "synced"
        logger.info("[Startup] Azure Blob Storage not configured; skipping startup data hydration.")
        return

    config_prefix_base =  "nutrifaq-config"
    dbase_main_prefix_base = "nutrifaq-dbase-main"

    config_target_root = PROJECT_ROOT / "nutrifaq-config"
    dbase_main_target_root = PROJECT_ROOT / "nutrifaq-dbase-main"
    dbase_prod_target_root = PROJECT_ROOT / "nutrifaq-dbase-prod"

    hydrated_targets: list[Path] = []

    try:
        # Refresh in-memory prod config from blob so downstream sync uses the global cache.
        loaded_config = load_prod_config(force_reload=True)
        logger.info("[Startup] Loaded prod config in memory (%s keys).", len(loaded_config))
    except Exception as exc:
        logger.warning("[Startup] Prod config load skipped: %s", exc)

    try:
        _load_refusal_config_from_blob()
    except Exception as exc:
        logger.warning("[Startup] Refusal config blob load skipped: %s", exc)


    try:
        # Sync only when the local main KB does not already contain files.
        local_has_files = dbase_main_target_root.exists() and any(dbase_main_target_root.rglob("*"))
        if local_has_files:
            logger.info(
                "[Startup] Main KB sync skipped: local folder already contains files (%s).",
                dbase_main_target_root,
            )
        else:
            sync_blob_prefix_to_local(
                prefix="",
                container_name=f"{dbase_main_prefix_base}",
                local_root=dbase_main_target_root,
                remove_existing=False

            )
            hydrated_targets.append(dbase_main_target_root)
            logger.info(
                "[Startup] Loaded blob main KB into %s (prefix=%s)",
                dbase_main_target_root,
                dbase_main_prefix_base,
            )
    except Exception as exc:
        logger.warning("[Startup] Main KB hydration skipped: %s", exc)

    try:
        documents_root = dbase_main_target_root / "documents"
        if documents_root.exists() and any(documents_root.rglob("*")):
            uploaded = sync_local_directory_to_blob(
                source_root=documents_root,
                destination_prefix="documents",
                container_name=dbase_main_prefix_base,
                overwrite=True,
            )
            logger.info(
                "[Startup] Synced %s local document files to Azure Blob Storage (container=%s, prefix=documents)",
                len(uploaded),
                dbase_main_prefix_base,
            )
        else:
            logger.info("[Startup] No local document files to sync back to Azure Blob Storage.")
    except Exception as exc:
        logger.warning("[Startup] Local document sync to blob skipped: %s", exc)

    try:
        # Copy the Chroma database from the main KB to the production folder.
        source_chroma, target_chroma, current_prod_sqlite, new_prod_sqlite = sync_next_prod_chroma_from_main()

        hydrated_targets.append(target_chroma)
        logger.info(
            "[Startup] Copied %s to %s (PROD_SQLITE old=%s, new=%s)",
            source_chroma,
            target_chroma,
            current_prod_sqlite or 'unset',
            new_prod_sqlite,
        )
    except Exception as exc:
        logger.warning("[Startup] Chroma copy to prod folder skipped: %s", exc)


    if app is not None:
        app.state.database_sync_status = "synced"
    if hydrated_targets:
        hydrated_labels = ", ".join(str(path) for path in hydrated_targets)
        logger.info("[Startup] Hydrated local targets: %s", hydrated_labels)

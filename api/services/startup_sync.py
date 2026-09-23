from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from api.services.blob_storage_service import (
    has_blob_storage_config,
    sync_blob_prefix_to_local,
    upload_file_to_blob,
)
from api.services.config import load_prod_config, sync_next_prod_chroma_from_main
from api.services.refusal_engine import load_refusal_patterns, load_refusal_responses

if TYPE_CHECKING:
    from fastapi import FastAPI

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _sync_prompts_config_to_blob() -> None:
    """Upload static/config/prompts.json to nutrifaq-config container."""
    config_container = os.getenv("AZURE_CONFIG_BLOB_CONTAINER", "nutrifaq-config").strip()
    config_prefix = os.getenv("AZURE_CONFIG_BLOB_PREFIX", "").strip("/")
    source_path = PROJECT_ROOT / "static" / "config" / "prompts.json"

    if not source_path.exists():
        raise FileNotFoundError(f"Missing local prompts source: {source_path}")

    blob_name = f"{config_prefix}/prompts.json" if config_prefix else "prompts.json"
    upload_file_to_blob(
        blob_name=blob_name,
        source_path=source_path,
        overwrite=True,
        container_name=config_container,
    )
    print(
        f"[Startup] Uploaded prompts config blob '{blob_name}' to container '{config_container}'.",
        flush=True,
    )


def _load_refusal_config_from_blob() -> None:
    """Load refusal config directly from nutrifaq-config container (no local fallback)."""
    patterns = load_refusal_patterns()
    responses = load_refusal_responses()
    print(
        f"[Startup] Loaded refusal config from blob (patterns languages={len(patterns)}, responses languages={len(responses)}).",
        flush=True,
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

    if not has_blob_storage_config():
        if app is not None:
            app.state.database_sync_status = "synced"
        print("[Startup] Azure Blob Storage not configured; skipping startup data hydration.", flush=True)
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
        print(f"[Startup] Loaded prod config in memory ({len(loaded_config)} keys).", flush=True)
    except Exception as exc:
        print(f"[Startup] Prod config load skipped: {exc}", flush=True)

    try:
        _sync_prompts_config_to_blob()
    except Exception as exc:
        print(f"[Startup] Prompts config blob sync skipped: {exc}", flush=True)

    try:
        _load_refusal_config_from_blob()
    except Exception as exc:
        print(f"[Startup] Refusal config blob load skipped: {exc}", flush=True)


    try:
        # Sync the main knowledge base from the blob storage to the local project root.
        sync_blob_prefix_to_local(
            prefix="",
            container_name=f"{dbase_main_prefix_base}",
            local_root=dbase_main_target_root,
            remove_existing=False

        )
        hydrated_targets.append(dbase_main_target_root)
        print(
            f"[Startup] Loaded blob main KB into {dbase_main_target_root} "
            f"(prefix={dbase_main_prefix_base})",
            flush=True,
        )
    except Exception as exc:
        print(
            f"[Startup] Main KB hydration skipped: {exc}",
            flush=True,
        )

    try:
        # Copy the Chroma database from the main KB to the production folder.
        source_chroma, target_chroma, current_prod_sqlite, new_prod_sqlite = sync_next_prod_chroma_from_main()

        hydrated_targets.append(target_chroma)
        print(
            f"[Startup] Copied {source_chroma} to {target_chroma} "
            f"(PROD_SQLITE old={current_prod_sqlite or 'unset'}, new={new_prod_sqlite})",
            flush=True,
        )
    except Exception as exc:
        print(f"[Startup] Chroma copy to prod folder skipped: {exc}", flush=True)


    if app is not None:
        app.state.database_sync_status = "synced"
    if hydrated_targets:
        hydrated_labels = ", ".join(str(path) for path in hydrated_targets)
        print(f"[Startup] Hydrated local targets: {hydrated_labels}", flush=True)

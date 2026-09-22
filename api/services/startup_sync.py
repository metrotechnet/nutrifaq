from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from api.services.blob_storage_service import (
    get_blob_prefix,
    has_blob_storage_config,
    sync_blob_prefix_to_local,
)
from api.services.query_chromadb import get_debug_local_kb_root_folder

if TYPE_CHECKING:
    from fastapi import FastAPI

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def sync_blob_databases_on_startup(app: "FastAPI | None" = None) -> None:
    """Hydrate the main and debug KBs from Blob Storage at startup."""
    if app is not None:
        app.state.database_sync_status = "synch"

    if not has_blob_storage_config():
        if app is not None:
            app.state.database_sync_status = "synch"
        print("[Startup] Azure Blob Storage not configured; skipping database hydration.", flush=True)
        return

    main_prefix = f"{get_blob_prefix()}/chroma_db/"
    main_target_root = PROJECT_ROOT / "nutrifaq-dbase" / "chroma_db"

    debug_container = os.getenv("AZURE_KB_DEBUG_BLOB_CONTAINER", "nutrifaq-knowledge-base-debug").strip()
    debug_prefix_base = os.getenv("AZURE_KB_DEBUG_BLOB_PREFIX", "nutrifaq-dbase-debug").strip("/")
    debug_prefix = f"{debug_prefix_base}/chroma_db/"
    debug_local_root = get_debug_local_kb_root_folder()
    debug_target_root = PROJECT_ROOT / debug_local_root / "chroma_db"
    debug_full_root = PROJECT_ROOT / debug_local_root

    hydrated_targets: list[str] = []

    try:
        sync_blob_prefix_to_local(prefix=main_prefix, local_root=main_target_root, remove_existing=False)
        hydrated_targets.append(str(main_target_root))
        print(f"[Startup] Loaded main blob ChromaDB into {main_target_root}", flush=True)
    except Exception as exc:
        print(f"[Startup] Main blob ChromaDB hydration skipped: {exc}", flush=True)

    try:
        sync_blob_prefix_to_local(
            prefix=f"{debug_prefix_base}/",
            local_root=debug_full_root,
            remove_existing=False,
            container_name=debug_container,
        )
        if str(debug_full_root) not in hydrated_targets:
            hydrated_targets.append(str(debug_full_root))
        print(
            f"[Startup] Loaded full debug blob root into {debug_full_root} "
            f"(container={debug_container}, prefix={debug_prefix_base}, local_root={debug_local_root})",
            flush=True,
        )
    except Exception as exc:
        print(
            f"[Startup] Full debug blob root hydration skipped: {exc} "
            f"(container={debug_container}, prefix={debug_prefix_base}, local_root={debug_local_root})",
            flush=True,
        )

    try:
        sync_blob_prefix_to_local(
            prefix=debug_prefix,
            local_root=debug_target_root,
            remove_existing=False,
            container_name=debug_container,
        )
        if str(debug_target_root) not in hydrated_targets:
            hydrated_targets.append(str(debug_target_root))
        print(
            f"[Startup] Loaded debug blob ChromaDB into {debug_target_root} "
            f"(container={debug_container}, prefix={debug_prefix_base}, local_root={debug_local_root})",
            flush=True,
        )
    except Exception as exc:
        print(
            f"[Startup] Debug blob ChromaDB hydration skipped: {exc} "
            f"(container={debug_container}, prefix={debug_prefix_base}, local_root={debug_local_root})",
            flush=True,
        )

    if app is not None:
        app.state.database_sync_status = "synch"
    if hydrated_targets:
        print(f"[Startup] Hydrated KB roots: {', '.join(hydrated_targets)}", flush=True)

"""
Configuration Management Utilities

This module provides functions for loading and merging configuration files in the Nutrifaq Agent backend.
"""
from pathlib import Path
import json
import os
import shutil
from threading import RLock
from typing import Any, Optional
from api.services.blob_storage_service import get_container_client, has_blob_storage_config


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
FRONTEND_CONFIG_ROOT = REPO_ROOT / "static" / "config"
SHARED_CONFIG_ROOT = REPO_ROOT / "nutrifaq-config"
LEGACY_CONFIG_ROOT = API_ROOT / "config"
PROD_CONFIG_PATH = SHARED_CONFIG_ROOT / "prod_config.json"

_PROD_CONFIG_LOCK = RLock()
_GLOBAL_PROD_CONFIG: dict[str, Any] = {}


def _config_blob_container_name() -> str:
    return os.getenv("AZURE_CONFIG_BLOB_CONTAINER", "nutrifaq-config").strip()


def _config_blob_prefix() -> str:
    return os.getenv("AZURE_CONFIG_BLOB_PREFIX", "").strip("/")


def _prod_config_blob_name() -> str:
    prefix = _config_blob_prefix()
    return f"{prefix}/prod_config.json" if prefix else "prod_config.json"


def _resolve_config_path(file_name: str) -> Path:
    frontend_path = FRONTEND_CONFIG_ROOT / file_name
    if frontend_path.exists():
        return frontend_path
    shared_path = SHARED_CONFIG_ROOT / file_name
    if shared_path.exists():
        return shared_path
    return LEGACY_CONFIG_ROOT / file_name


def deep_merge(base_config: dict, override_config: dict) -> dict:
    """
    Deep merge two configuration dictionaries.
    Override values take precedence over base values.

    Args:
        base_config (dict): Base configuration dictionary.
        override_config (dict): Override configuration dictionary.

    Returns:
        dict: Merged configuration dictionary.
    """
    result = base_config.copy()
    
    for key, value in override_config.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dictionaries
            result[key] = deep_merge(result[key], value)
        else:
            # Override value
            result[key] = value
    
    return result


def get_config():
    """
    Get configuration for single-agent deployment.
    Merges common config with agent-specific config.
    Agent config takes precedence over common config.

    Returns:
        dict: Configuration dictionary for the agent.
    """
    try:
        
        # Load common config (base configuration)
        common_config_path = _resolve_config_path("common_config.json")
        common_config = {}
        if common_config_path.exists():
            with open(common_config_path, 'r', encoding='utf-8') as f:
                common_config = json.load(f)
        
        # Load agent-specific config (override configuration)
        agent_config_path = _resolve_config_path("agent_config.json")
        
        if agent_config_path.exists():
            with open(agent_config_path, 'r', encoding='utf-8') as f:
                agent_config = json.load(f)
            
            # Merge: common config as base, agent config as override
            return deep_merge(common_config, agent_config)
        
        # If agent config doesn't exist but common does, return common
        if common_config:
            return common_config
        
        # Provide detailed error with debugging info
        kb_dir = REPO_ROOT / "nutrifaq-dbase"
        available_kbs = []
        if kb_dir.exists():
            available_kbs = [d.name for d in kb_dir.iterdir() if d.is_dir()]
        
        return {
            "error": f"config not found at {agent_config_path}",
            "debug": {
                "project_root": str(REPO_ROOT),
                "config_path": str(agent_config_path),
                "common_config_path": str(common_config_path),
                "kb_dir_exists": kb_dir.exists(),
                "available_knowledge_bases": available_kbs
            }
        }
        
    except FileNotFoundError:
        agent_config_path = _resolve_config_path("agent_config.json")
        return {
            "error": f"config not found at {agent_config_path}",
            "debug": {"config_path": str(agent_config_path)}
        }
    except Exception as e:
        agent_config_path = _resolve_config_path("agent_config.json")
        return {
            "error": f"Error loading config from {agent_config_path}: {str(e)}",
            "debug": {"config_path": str(agent_config_path)}
        }


def load_prod_config(force_reload: bool = False) -> dict[str, Any]:
    """Load prod_config.json from Azure Blob into global memory and return it."""
    global _GLOBAL_PROD_CONFIG

    with _PROD_CONFIG_LOCK:
        if _GLOBAL_PROD_CONFIG and not force_reload:
            return _GLOBAL_PROD_CONFIG.copy()

        if not has_blob_storage_config():
            raise RuntimeError("Azure Blob Storage is required to load prod config.")

        blob_name = _prod_config_blob_name()
        blob_client = get_container_client(_config_blob_container_name()).get_blob_client(blob_name)

        try:
            raw_content = blob_client.download_blob().readall()
        except Exception as exc:
            message = str(exc)
            if "BlobNotFound" in message or "The specified blob does not exist" in message:
                _GLOBAL_PROD_CONFIG = {}
                return _GLOBAL_PROD_CONFIG.copy()
            raise

        data = json.loads(raw_content.decode("utf-8"))

        if not isinstance(data, dict):
            raise ValueError(f"Invalid JSON root in blob '{blob_name}': expected an object.")

        _GLOBAL_PROD_CONFIG = data
        return _GLOBAL_PROD_CONFIG.copy()


def save_prod_config(data: dict[str, Any]) -> dict[str, Any]:
    """Save provided config directly to Azure Blob and update global memory."""
    global _GLOBAL_PROD_CONFIG

    if not isinstance(data, dict):
        raise TypeError("save_prod_config expects a dictionary.")

    with _PROD_CONFIG_LOCK:
        if not has_blob_storage_config():
            raise RuntimeError("Azure Blob Storage is required to save prod config.")

        blob_name = _prod_config_blob_name()
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        blob_client = get_container_client(_config_blob_container_name()).get_blob_client(blob_name)
        blob_client.upload_blob(payload, overwrite=True)

        _GLOBAL_PROD_CONFIG = data.copy()
        return _GLOBAL_PROD_CONFIG.copy()


def update_prod_config(values: dict[str, Any], deep: bool = True) -> dict[str, Any]:
    """Update global prod config values and persist to nutrifaq-config/prod_config.json."""
    if not isinstance(values, dict):
        raise TypeError("update_prod_config expects a dictionary.")

    with _PROD_CONFIG_LOCK:
        current = load_prod_config(force_reload=False)
        updated = deep_merge(current, values) if deep else {**current, **values}
        return save_prod_config(updated)


def next_chroma_target_dirname(prod_sqlite_value: str | None) -> str:
    """Return the alternate local Chroma folder name based on PROD_SQLITE."""
    current_name = Path((prod_sqlite_value or "").strip()).name
    if current_name == "chroma_db_0":
        return "chroma_db_1"
    if current_name == "chroma_db_1":
        return "chroma_db_0"
    return "chroma_db_0"


def resolve_chroma_copy_paths(
    prod_config: dict[str, Any],
    dbase_main_target_root: Path,
    dbase_prod_target_root: Path,
) -> tuple[Path, Path, str]:
    """Resolve source/target Chroma paths from config values for startup sync."""
    current_debug_sqlite = str(prod_config.get("DEBUG_SQLITE", "") or "")
    source_chroma = dbase_main_target_root / current_debug_sqlite

    current_prod_sqlite = str(prod_config.get("PROD_SQLITE", "") or "")
    target_dirname = next_chroma_target_dirname(current_prod_sqlite)
    target_chroma = dbase_prod_target_root / target_dirname
    return source_chroma, target_chroma, current_prod_sqlite


def sync_next_prod_chroma_from_main(
    prod_config: dict[str, Any],
    dbase_main_target_root: Path,
    dbase_prod_target_root: Path,
) -> tuple[Path, Path, str, str]:
    """Copy next Chroma folder from main to prod and persist new PROD_SQLITE."""
    source_chroma, target_chroma, current_prod_sqlite = resolve_chroma_copy_paths(
        prod_config,
        dbase_main_target_root,
        dbase_prod_target_root,
    )

    if not source_chroma.exists():
        raise FileNotFoundError(f"Source Chroma path not found: {source_chroma}")

    dbase_prod_target_root.mkdir(parents=True, exist_ok=True)
    if target_chroma.exists():
        shutil.rmtree(target_chroma, ignore_errors=True)

    shutil.copytree(source_chroma, target_chroma, dirs_exist_ok=True)

    new_prod_sqlite = f"{target_chroma.name}"
    update_prod_config({"PROD_SQLITE": new_prod_sqlite})

    return source_chroma, target_chroma, current_prod_sqlite, new_prod_sqlite

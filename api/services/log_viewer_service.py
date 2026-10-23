from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve_log_path() -> Path:
    configured_path = os.getenv("LOG_FILE_PATH", "logs/nutrifaq.log").strip()
    if not configured_path:
        configured_path = "logs/nutrifaq.log"

    log_path = Path(configured_path)
    if not log_path.is_absolute():
        log_path = (REPO_ROOT / log_path).resolve()
    return log_path


def read_log_text() -> str:
    log_path = resolve_log_path()
    if not log_path.exists():
        return ""
    return log_path.read_text(encoding="utf-8", errors="replace")


def clear_log_file() -> Path:
    log_path = resolve_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")
    return log_path


def get_log_metadata() -> dict[str, object]:
    log_path = resolve_log_path()
    exists = log_path.exists()
    size = log_path.stat().st_size if exists else 0
    return {
        "path": str(log_path),
        "exists": exists,
        "size_bytes": size,
        "size_human": f"{size} bytes",
    }

from __future__ import annotations

import logging
import os
from pathlib import Path

from api.services.blob_storage_service import download_blob_to_path

logger = logging.getLogger(__name__)


def main() -> int:
    container = os.getenv("AZURE_CONFIG_BLOB_CONTAINER", "nutrifaq-config").strip()
    prefix = os.getenv("AZURE_CONFIG_BLOB_PREFIX", "").strip("/")
    destination = Path("static/config/prompts.json")
    destination.parent.mkdir(parents=True, exist_ok=True)

    candidates: list[str] = []
    if prefix:
        candidates.append(f"{prefix}/prompts.json")
    candidates.append("prompts.json")

    errors: list[str] = []
    for blob_name in candidates:
        try:
            download_blob_to_path(blob_name, destination, container_name=container)
            logger.info("OK blob=%s", blob_name)
            logger.info("DEST=%s", destination.resolve())
            logger.info("SIZE=%s", destination.stat().st_size)
            return 0
        except Exception as exc:  # pragma: no cover - runtime dependent
            errors.append(f"{blob_name}: {type(exc).__name__}: {exc}")

    logger.error("FAILED all candidates")
    for err in errors:
        logger.error(err)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

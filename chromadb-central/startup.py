"""Azure App Service entrypoint for ChromaDB Central.

This bootstraps Python dependencies when the App Service starts, then
launches the FastAPI app with Uvicorn.
"""

from __future__ import annotations

import os
import subprocess
import sys


def ensure_requirements_installed() -> None:
    requirements_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if not os.path.exists(requirements_path):
        return

    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
        return
    except ImportError:
        pass

    subprocess.check_call([
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-cache-dir",
        "-r",
        requirements_path,
    ])


def main() -> None:
    ensure_requirements_installed()

    import uvicorn
    from app import app

    port = int(os.environ.get("PORT", "2000"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
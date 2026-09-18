# =====================================================
# Imports - Main application imports
# =====================================================
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path
import importlib
from api.services.blob_storage_service import (
    get_blob_prefix,
    has_blob_storage_config,
    sync_blob_prefix_to_local,
)
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# =====================================================
# Configuration & Application Setup
# =====================================================
PROJECT_ROOT = Path(__file__).parent
env_path = PROJECT_ROOT / '.env'
load_dotenv(dotenv_path=env_path)

import os

app = FastAPI(title="IMX Agent Factory - Nutria Agent API", version="1.0")
APP_VERSION = os.getenv("APP_VERSION", "dev")
app.state.database_sync_status = "synch"


@app.on_event("startup")
async def startup_load_blob_database():
    if not has_blob_storage_config():
        app.state.database_sync_status = "synch"
        print("[Startup] Azure Blob Storage not configured; skipping database hydration.", flush=True)
        return

    source_prefix = f"{get_blob_prefix()}/chroma_db/"
    target_root = PROJECT_ROOT / "nutrifaq-dbase" / "chroma_db"
    try:
        sync_blob_prefix_to_local(prefix=source_prefix, local_root=target_root, remove_existing=False)
        app.state.database_sync_status = "synch"
        print(f"[Startup] Loaded blob database into {target_root}", flush=True)
    except Exception as exc:
        app.state.database_sync_status = "synch"
        print(f"[Startup] Blob database hydration skipped: {exc}", flush=True)

# =====================================================
# Rate Limiting Configuration
# =====================================================
# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["30 per day", "10 per hour"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS with dynamic origins

# Build allowed origins dynamically
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:8080",
    "http://localhost:5000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:5000"
]

# Allow additional origins from ADDITIONAL_CORS_ORIGINS env var (comma-separated)
additional_origins = os.getenv("ADDITIONAL_CORS_ORIGINS", "")
if additional_origins:
    allowed_origins.extend([origin.strip() for origin in additional_origins.split(",") if origin.strip()])

# Deduplicate while preserving order
allowed_origins = list(dict.fromkeys(allowed_origins))

default_origin_regex = (
    r"^https://nutrifaq[a-z0-9-]*\.z\d+\.web\.core\.windows\.net$"
    r"|^http://(?:localhost|127\.0\.0\.1)(?::\d+)?$"
)

additional_origin_regex = os.getenv("ADDITIONAL_CORS_ORIGIN_REGEX", "").strip()
allow_origin_regex = default_origin_regex
if additional_origin_regex:
    allow_origin_regex = f"(?:{default_origin_regex})|(?:{additional_origin_regex})"

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# Include API Routes
# =====================================================
ROUTE_MODULES = [
    ("api.routes.users", "users"),
    ("api.routes.query", "query"),
    ("api.routes.translation", "translation"),
    ("api.routes.tts", "tts"),
    ("api.routes.report", "report"),
    ("api.routes.config", "config"),
    ("api.routes.sessions", "sessions"),
    ("api.routes.blob", "blob"),
    ("api.routes.database", "database"),
]

for module_name, tag in ROUTE_MODULES:
    try:
        module = importlib.import_module(module_name)
        app.include_router(module.router, tags=[tag])
    except Exception as exc:
        # Keep the service alive even if one optional integration fails at startup.
        print(f"Route '{module_name}' not loaded: {exc}")

# =====================================================
# Main Routes
# =====================================================
@app.get("/")
def home():
    """API root endpoint - frontend is hosted on Firebase"""
    return {
        "status": "ok",
        "message": "IMX Agent Factory API",
        "app_version": APP_VERSION,
    }


@app.get("/health")
def health():
    """Health check endpoint"""
    return {
        "status": "ok",
        "app_version": APP_VERSION,
    }
# =====================================================
# Run Application
# =====================================================
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
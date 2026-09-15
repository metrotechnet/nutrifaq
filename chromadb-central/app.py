# Endpoint générique pour requêter n'importe quelle collection d'un projet
from fastapi import Body
from api.query_chromadb import get_collection
from api.orchestrator import smart_query
from api.graph_layer import preload_graphs
from api.routes import query, update, datasets
import os

"""
ChromaDB Central API
Provides access to multiple project vector databases (Bibliosense, Nutria, Translator).
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import asynccontextmanager
from api.query_chromadb import list_collections, query_vector_db, preload_all_collections

# Use FastAPI lifespan context for startup/shutdown logic
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 60, flush=True)
    print("🚀 Starting IMX Agent Factory...", flush=True)
    print("=" * 60, flush=True)
    try:
        if os.getenv("K_SERVICE"):
            # Deployed on Cloud Run: download from GCS bucket and load
            preload_all_collections()
        else:
            # Local dev: load from local knowledge-base/ only
            preload_all_collections(local_only=True)
        from api.query_chromadb import list_collections, _PRELOADED_COLLECTIONS
        for db in _PRELOADED_COLLECTIONS:
            collections = list_collections(db)
            if collections:
                print(f"✅ ChromaDB loaded successfully!", flush=True)
                print(f"   - Project: {db}", flush=True)
                print(f"   - Collections found:", flush=True)
                for col in collections:
                    print(f"     • {col.name} (count: {col.count()})", flush=True)
            else:
                print(f"⚠️  Warning: No ChromaDB collection found for '{db}'", flush=True)
                print(f"   Database will be loaded on first query", flush=True)
    except Exception as e:
        print(f"⚠️  Warning: Failed to preload ChromaDB: {str(e)}", flush=True)
        print(f"   Database will be loaded on first query", flush=True)

    print("=" * 60, flush=True)
    print("✅ Application startup complete", flush=True)
    print("=" * 60, flush=True)
    yield
    print("🛑 Shutting down IMX Agent Factory...", flush=True)

app = FastAPI(title="IMX Agent Factory - ChromaDB Central API", lifespan=lifespan)

# CORS for Firebase-hosted frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# Include API Routes
# =====================================================
app.include_router(query.router, tags=["query"])
app.include_router(update.router, tags=["update"])
app.include_router(datasets.router, tags=["datasets"])

# =====================================================
# Main Routes
# =====================================================
@app.get("/")
def home():
    """API root endpoint - frontend is hosted on Firebase"""
    return {"status": "ok", "message": "ChromaDB Central API is running."}


@app.get("/health")
def health():
    """Health check endpoint"""
    return {"status": "ok"}


# =====================================================
# Run Application
# =====================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 2000))
    uvicorn.run(app, host="0.0.0.0", port=port)
"""
Minimal ChromaDB access layer for central API.
"""
import os
import subprocess
from dotenv import load_dotenv
from chromadb.config import Settings
from chromadb.utils import embedding_functions
import chromadb
from google.cloud import storage

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

OPENAI_API_KEY = os.getenv("AI_GATEWAY_API_KEY") or os.getenv("OPENAI_API_KEY")
OPENAI_API_BASE = os.getenv("AI_GATEWAY_BASE_URL", "https://ai-gateway.vercel.sh/v1")

GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "agent-factory-database")

# Embedding model per project (innovia uses small, others use large)
_EMBEDDING_MODELS = {
    "innovia": "text-embedding-3-small",
}
_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"


# Global cache for preloaded collections
_PRELOADED_COLLECTIONS = {}

# Helper to list collections for a project
def list_collections(project_name):
    if project_name in _PRELOADED_COLLECTIONS:
        return list(_PRELOADED_COLLECTIONS[project_name].values())
    return []

# Helper to get collection for a project (optionally by name)
def get_collection(project_name, collection_name=None):
    # Return preloaded collection if available and no name specified
    if collection_name is None and project_name in _PRELOADED_COLLECTIONS:
        # Peut être None si preload a échoué
        print(f"[Get Collection] Returning preloaded collection for project '{project_name}'")
        return next(iter(_PRELOADED_COLLECTIONS[project_name].values()), None)
    elif collection_name is not None and project_name in _PRELOADED_COLLECTIONS:
        return _PRELOADED_COLLECTIONS[project_name].get(collection_name)
    return None

# Preload all collections (to be called at startup)
def preload_all_collections(project_names=None, local_only=False):
    """
    Load all ChromaDB collections.
    - local_only=True: load from local knowledge-base/ folders only (no GCS download).
    - local_only=False: download chroma_db from GCS bucket first, then load.
    If project_names is None, auto-discover from bucket (or local folders if local_only).
    """
    kb_root = os.path.join(PROJECT_ROOT, "knowledge-base")

    # --- Step 1: Discover projects ---
    if project_names is None:
        if local_only:
            # Discover from local knowledge-base/ subfolders
            project_names = [
                d for d in os.listdir(kb_root)
                if os.path.isdir(os.path.join(kb_root, d, "chroma_db"))
            ] if os.path.isdir(kb_root) else []
            print(f"[Preload] Local projects found: {project_names}", flush=True)
        else:
            project_names = _discover_projects_from_bucket()
            print(f"[Preload] Discovered projects from bucket: {project_names}", flush=True)

    # --- Step 2: Download from bucket (skip if local_only) ---
    if not local_only:
        for project_name in project_names:
            try:
                _download_chroma_db_from_bucket(project_name, kb_root)
            except Exception as e:
                print(f"[Preload] Failed to download chroma_db for {project_name}: {e}", flush=True)

    # --- Step 3: Load collections into memory ---
    for project_name in project_names:
        try:
            kb_path = os.path.join(kb_root, project_name, "chroma_db")
            if not os.path.exists(kb_path):
                print(f"[Preload] No chroma_db folder for {project_name}, skipping.", flush=True)
                continue

            client = chromadb.PersistentClient(path=kb_path, settings=Settings(anonymized_telemetry=False, allow_reset=False))
            all_collections = client.list_collections()

            model_name = _EMBEDDING_MODELS.get(project_name, _DEFAULT_EMBEDDING_MODEL)
            ef = embedding_functions.OpenAIEmbeddingFunction(
                api_key=OPENAI_API_KEY, model_name=model_name,
                api_base=OPENAI_API_BASE,
            )

            if all_collections:
                for col in all_collections:
                    print(f"[Preload] Found collection for {project_name}: {col.name}", flush=True)
                    collection = client.get_collection(name=col.name)
                    collection._embedding_function = ef
                    if project_name not in _PRELOADED_COLLECTIONS:
                        _PRELOADED_COLLECTIONS[project_name] = {}
                    _PRELOADED_COLLECTIONS[project_name][col.name] = collection

        except Exception as e:
            print(f"[Preload] Failed to preload collection for {project_name}: {e}", flush=True)


def _discover_projects_from_bucket():
    """List top-level folders in the GCS bucket to discover project names."""
    try:
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET_NAME)
        # List top-level prefixes (folders)
        blobs = client.list_blobs(bucket, delimiter="/")
        # Must consume the iterator to populate prefixes
        _ = list(blobs)
        projects = [p.rstrip("/") for p in blobs.prefixes]
        return projects
    except Exception as e:
        print(f"[Discover] Failed to list projects from bucket: {e}", flush=True)
        return []


def _download_chroma_db_from_bucket(project_name, kb_root):
    """Download chroma_db folder from GCS bucket to local knowledge-base."""
    gcs_prefix = f"{project_name}/chroma_db/"
    local_dir = os.path.join(kb_root, project_name, "chroma_db")
    os.makedirs(local_dir, exist_ok=True)

    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET_NAME)
    blobs = list(client.list_blobs(bucket, prefix=gcs_prefix))

    if not blobs:
        print(f"[Download] No files found in gs://{GCS_BUCKET_NAME}/{gcs_prefix}", flush=True)
        return

    count = 0
    for blob in blobs:
        # Skip "directory" markers
        if blob.name.endswith("/"):
            continue
        # Preserve folder structure relative to chroma_db/
        relative_path = blob.name[len(gcs_prefix):]
        local_path = os.path.join(local_dir, relative_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        blob.download_to_filename(local_path)
        count += 1

    print(f"[Download] Downloaded {count} files for {project_name}/chroma_db", flush=True)


def reload_project_collections(project_name,collection_name=None):
    """Reload collections for a single project after an update/re-index."""
    try:
        kb_path = os.path.join(PROJECT_ROOT, "knowledge-base", project_name, "chroma_db")
        client = chromadb.PersistentClient(path=kb_path, settings=Settings(anonymized_telemetry=False, allow_reset=False))
        all_collections = client.list_collections()

        model_name = _EMBEDDING_MODELS.get(project_name, _DEFAULT_EMBEDDING_MODEL)
        ef = embedding_functions.OpenAIEmbeddingFunction(
            api_key=OPENAI_API_KEY, model_name=model_name,
            api_base=OPENAI_API_BASE,
        )

        _PRELOADED_COLLECTIONS.setdefault(project_name, {})
        if collection_name:
            # Reload only the specified collection
            collection = client.get_collection(name=collection_name)
            collection._embedding_function = ef
            _PRELOADED_COLLECTIONS[project_name][collection_name] = collection
            print(f"[Reload] Refreshed collection for {project_name}: {collection_name} ({collection.count()} items)")
        else:
            # Reload all collections
            _PRELOADED_COLLECTIONS[project_name] = {}
            for col in all_collections:
                collection = client.get_collection(name=col.name)
                collection._embedding_function = ef
                _PRELOADED_COLLECTIONS[project_name][col.name] = collection
                print(f"[Reload] Refreshed collection for {project_name}: {col.name} ({collection.count()} items)")
    except Exception as e:
        print(f"[Reload] Failed to reload collections for {project_name}: {e}")


# Example query function (to be adapted for your schema)
def query_vector_db(project_name, collection_name, query):

    collection = get_collection(project_name, collection_name)
    if collection is None:
        return {"error": "ChromaDB collection is not available. Please run 'python index_chromadb.py' first to index your documents."}
    
    # If query is a dict, treat as advanced vector search
    if isinstance(query, dict):
        # Expecting keys: query_embedding, n_results, include, (optional) where
        try:
            query_embedding = query["query_embedding"]
            n_results = query.get("n_results", 10)
            include = query.get("include", ["documents"])
            where = query.get("where")
            query_args = {
                "query_embeddings": [query_embedding],
                "n_results": n_results,
                "include": include
            }
            if where:
                query_args["where"] = where
            results = collection.query(**query_args)
            return results
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"Invalid vector search payload or ChromaDB error: {str(e)}"}
    # Else, treat as simple question string
    return {"project": project_name, "question": query, "result": "(vector search result here)"}


def extract_entities(results):
    entities = []

    for meta in results.get("metadatas", [[]])[0]:
        if "name" in meta:
            entities.append(meta["name"])

    return list(set(entities))
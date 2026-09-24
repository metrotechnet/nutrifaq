"""
Index ChromaDB from transcripts_chromadb.json.

Usage:
    python index_chromadb_json.py <knowledge_base_path>
"""

import json
import os
import shutil
import sys
import time
from pathlib import Path

import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.services.blob_storage_service import (  # noqa: E402
    download_blob_to_path,
    get_blob_container_name,
    get_blob_prefix,
)
from api.services.llm_service import create_embeddings  # noqa: E402
from api.services.database_regeneration_service import _write_progress_snapshot  # noqa: E402

# Get main root directory (where .env is located)
MAIN_ROOT = Path.cwd()
while not (MAIN_ROOT / ".env").exists() and MAIN_ROOT.parent != MAIN_ROOT:
    MAIN_ROOT = MAIN_ROOT.parent

load_dotenv(dotenv_path=MAIN_ROOT / ".env", override=True)

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_ACCOUNT = os.getenv("AZURE_STORAGE_ACCOUNT")
AZURE_STORAGE_KEY = os.getenv("AZURE_STORAGE_KEY")
AZURE_STORAGE_SAS_TOKEN = os.getenv("AZURE_STORAGE_SAS_TOKEN")
AZURE_STORAGE_CONTAINER = get_blob_container_name()
AZURE_BLOB_PREFIX = get_blob_prefix()


def _sync_transcripts_json_from_blob(kb_path: Path) -> Path:
    local_json = kb_path / "transcripts_chromadb.json"
    if local_json.exists():
        return local_json

    blob_name = f"{AZURE_BLOB_PREFIX}/transcripts_chromadb.json"
    kb_path.mkdir(parents=True, exist_ok=True)
    try:
        download_blob_to_path(blob_name, local_json)
    except Exception as exc:
        raise FileNotFoundError(
            f"transcripts_chromadb.json not found locally and not available in blob: {blob_name}"
        ) from exc
    return local_json


def get_embeddings(texts):
    """Get embeddings using the configured embedding provider."""
    if isinstance(texts, str):
        texts = [texts]
    return create_embeddings(input_texts=texts, model_name="text-embedding-3-large")


def init_chromadb(kb_path):
    """Initialize ChromaDB client for a specific knowledge base."""
    kb_path = Path(kb_path)
    chroma_path = str(kb_path / "chroma_db")

    os.makedirs(chroma_path, exist_ok=True)

    chroma_client = chromadb.PersistentClient(
        path=chroma_path,
        settings=Settings(
            anonymized_telemetry=False,
            allow_reset=False,
        ),
    )

    collection_name = "nutrifaq-collection"

    try:
        chroma_client.delete_collection(name=collection_name)
        print(f"Deleted existing collection: {collection_name}")
    except Exception:
        pass

    collection = chroma_client.create_collection(
        name=collection_name,
        metadata={"description": f"Knowledge base: {kb_path.name}"},
    )

    return chroma_client, collection


def _reset_chroma_directory(kb_path: Path) -> None:
    chroma_path = kb_path / "chroma_db"
    if chroma_path.exists():
        shutil.rmtree(chroma_path, ignore_errors=True)


def _is_missing_collections_table_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "no such table: collections" in message or "error getting collection" in message


def chunk_text(text, chunk_size=1000, overlap=100):
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        start = end - overlap
    return chunks


def index_chromadb_json(kb_path):
    """Index ChromaDB-compatible JSON into ChromaDB."""
    kb_path = Path(kb_path)
    json_file = _sync_transcripts_json_from_blob(kb_path)

    if not json_file.exists():
        print(f"File not found: {json_file}")
        print("Ensure transcripts_chromadb.json was created first")
        return

    embedding_provider = os.getenv("EMBEDDING_PROVIDER", os.getenv("LLM_PROVIDER", "vercel"))
    print(f"Embedding provider: {embedding_provider}")
    print(f"Loading JSON from: {json_file}")

    if json_file.stat().st_size == 0:
        print(f"Error: {json_file} is empty.")
        print("Run generate_transcripts_json first and ensure it produced valid content.")
        return

    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {json_file} ({exc}).")
        print("Run generate_transcripts_json first and ensure it produced valid content.")
        return

    documents = data.get("documents", [])
    if not documents:
        print("No documents found in JSON file")
        return

    # Always start from a clean local ChromaDB folder before indexing.
    _reset_chroma_directory(kb_path)

    print(f"Found {len(documents)} documents to index\n")

    try:
        _, collection = init_chromadb(kb_path)
    except Exception as exc:
        if _is_missing_collections_table_error(exc):
            print("ChromaDB schema is missing or corrupted; recreating local database and retrying...")
            _reset_chroma_directory(kb_path)
            _, collection = init_chromadb(kb_path)
        else:
            raise

    all_ids = []
    all_documents = []
    all_embeddings = []
    all_metadatas = []

    total_chunks = 0
    total_tokens = sum(len(str(doc.get("text", "")).split()) for doc in documents)
    progress_total = max(total_tokens, 1)
    processed_tokens = 0
    _write_progress_snapshot("index_chromadb_json", 0, progress_total, "tokens")

    for doc in documents:
        doc_id = doc["id"]
        text = doc["text"]
        metadata = doc["metadata"]

        print(f"Processing: {doc_id}")

        chunks = chunk_text(text, chunk_size=1000, overlap=100)
        print(f"  Created {len(chunks)} chunks")
        total_chunks += len(chunks)

        chunk_embeddings = get_embeddings(chunks)

        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk{i}"
            all_ids.append(chunk_id)
            all_documents.append(chunk)
            all_embeddings.append(chunk_embeddings[i])

            chunk_metadata = {
                **metadata,
                "chunk_index": i,
                "total_chunks": len(chunks),
            }
            all_metadatas.append(chunk_metadata)

            processed_tokens += len(str(chunk).split())
            progress_value = min(processed_tokens, progress_total)
            _write_progress_snapshot("index_chromadb_json", progress_value, progress_total, "tokens")

        print(f"  Successfully prepared {doc_id}")
        time.sleep(0.05)

    print(f"\nIndexing {total_chunks} chunks into ChromaDB...")

    batch_size = 1000
    total_batches = (len(all_ids) + batch_size - 1) // batch_size

    for batch_idx in range(total_batches):
        start_idx = batch_idx * batch_size
        end_idx = min((batch_idx + 1) * batch_size, len(all_ids))

        batch_ids = all_ids[start_idx:end_idx]
        batch_documents = all_documents[start_idx:end_idx]
        batch_embeddings = all_embeddings[start_idx:end_idx]
        batch_metadatas = all_metadatas[start_idx:end_idx]

        print(f"   Batch {batch_idx + 1}/{total_batches}: Adding {len(batch_ids)} chunks...")

        try:
            collection.add(
                ids=batch_ids,
                documents=batch_documents,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
            )
        except Exception as exc:
            if _is_missing_collections_table_error(exc):
                print("ChromaDB schema error detected during indexing; rebuilding local database and retrying...")
                _reset_chroma_directory(kb_path)
                _, collection = init_chromadb(kb_path)
                collection.add(
                    ids=batch_ids,
                    documents=batch_documents,
                    embeddings=batch_embeddings,
                    metadatas=batch_metadatas,
                )
            else:
                raise

    # Ensure the step status ends exactly at 100% for UI polling.
    _write_progress_snapshot("index_chromadb_json", progress_total, progress_total, "tokens")

    print(f"\nSuccessfully indexed {total_chunks} chunks from {len(documents)} documents")
    print(f"Collection: {collection.name}")
    print(f"Total items: {collection.count()}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python index_chromadb_json.py <knowledge_base_path>")
        sys.exit(1)

    kb_path = Path(sys.argv[1])
    print(f"Starting ChromaDB indexing for: {kb_path}\n")
    print("=" * 60)
    index_chromadb_json(kb_path=kb_path)
    print("=" * 60)
    print("\nIndexing complete! Knowledge base is ready to be queried.")

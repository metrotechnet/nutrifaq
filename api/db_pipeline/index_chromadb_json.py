"""
Index ChromaDB from transcripts_chromadb.json.

Usage:
    python index_chromadb_json.py <knowledge_base_path>
"""

import json
import os
import sys
import shutil
from pathlib import Path

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
from openai import OpenAI
from api.services.blob_storage_service import (
    get_blob_container_name,
    get_blob_prefix,
    download_blob_to_path,
)


# Get main root directory (where .env is located)
MAIN_ROOT = Path.cwd()
while not (MAIN_ROOT / ".env").exists() and MAIN_ROOT.parent != MAIN_ROOT:
    MAIN_ROOT = MAIN_ROOT.parent

load_dotenv(dotenv_path=MAIN_ROOT / ".env", override=True)

client = OpenAI(
    api_key=os.getenv("AI_GATEWAY_API_KEY"),
    base_url="https://ai-gateway.vercel.sh/v1",
)

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_ACCOUNT = os.getenv("AZURE_STORAGE_ACCOUNT")
AZURE_STORAGE_KEY = os.getenv("AZURE_STORAGE_KEY")
AZURE_STORAGE_SAS_TOKEN = os.getenv("AZURE_STORAGE_SAS_TOKEN")
AZURE_STORAGE_CONTAINER = get_blob_container_name()
AZURE_BLOB_PREFIX = get_blob_prefix()


def _sync_transcripts_json_from_blob(kb_path: Path) -> Path:
    local_json = kb_path / "transcripts_chromadb.json"
    blob_name = f"{AZURE_BLOB_PREFIX}/transcripts_chromadb.json"
    kb_path.mkdir(parents=True, exist_ok=True)
    download_blob_to_path(blob_name, local_json)
    return local_json


def get_embeddings(texts):
    """Get embeddings from OpenAI."""
    if isinstance(texts, str):
        texts = [texts]

    batch_size = 100
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(model="text-embedding-3-large", input=batch)
        all_embeddings.extend([e.embedding for e in resp.data])

    return all_embeddings


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

    openai_api_key = os.getenv("OPENAI_API_KEY")
    ef = embedding_functions.OpenAIEmbeddingFunction(api_key=openai_api_key, model_name="text-embedding-3-large")

    try:
        chroma_client.delete_collection(name=collection_name)
        print(f"Deleted existing collection: {collection_name}")
    except Exception:
        pass

    collection = chroma_client.create_collection(
        name=collection_name,
        embedding_function=ef,
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

    print(f"Loading JSON from: {json_file}")
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    documents = data.get("documents", [])
    if not documents:
        print("No documents found in JSON file")
        return

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
    all_metadatas = []

    total_chunks = 0

    for doc in documents:
        doc_id = doc["id"]
        text = doc["text"]
        metadata = doc["metadata"]

        print(f"Processing: {doc_id}")

        chunks = chunk_text(text, chunk_size=1000, overlap=100)
        print(f"  Created {len(chunks)} chunks")
        total_chunks += len(chunks)

        _ = get_embeddings(chunks)

        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk{i}"
            all_ids.append(chunk_id)
            all_documents.append(chunk)

            chunk_metadata = {
                **metadata,
                "chunk_index": i,
                "total_chunks": len(chunks),
            }
            all_metadatas.append(chunk_metadata)

        print(f"  Successfully prepared {doc_id}")

    print(f"\nIndexing {total_chunks} chunks into ChromaDB...")

    batch_size = 1000
    total_batches = (len(all_ids) + batch_size - 1) // batch_size

    for batch_idx in range(total_batches):
        start_idx = batch_idx * batch_size
        end_idx = min((batch_idx + 1) * batch_size, len(all_ids))

        batch_ids = all_ids[start_idx:end_idx]
        batch_documents = all_documents[start_idx:end_idx]
        batch_metadatas = all_metadatas[start_idx:end_idx]

        print(f"   Batch {batch_idx + 1}/{total_batches}: Adding {len(batch_ids)} chunks...")

        try:
            collection.add(ids=batch_ids, documents=batch_documents, metadatas=batch_metadatas)
        except Exception as exc:
            if _is_missing_collections_table_error(exc):
                print("ChromaDB schema error detected during indexing; rebuilding local database and retrying...")
                _reset_chroma_directory(kb_path)
                _, collection = init_chromadb(kb_path)
                collection.add(ids=batch_ids, documents=batch_documents, metadatas=batch_metadatas)
            else:
                raise

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

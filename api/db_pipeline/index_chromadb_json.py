"""
Index ChromaDB from reviewed_documents.json.

Usage:
    python index_chromadb_json.py <knowledge_base_path>
"""

import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

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
from api.services.logging import configure_logging  # noqa: E402
from api.services.llm_service import create_embeddings  # noqa: E402
from api.services.database_regeneration_service import _write_progress_snapshot  # noqa: E402

configure_logging()

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


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _sync_reviewed_json_from_blob(kb_path: Path) -> Path:
    reviewed_json = kb_path / "reviewed_documents.json"
    if reviewed_json.exists():
        return reviewed_json

    blob_name = f"{AZURE_BLOB_PREFIX}/reviewed_documents.json"
    kb_path.mkdir(parents=True, exist_ok=True)
    try:
        download_blob_to_path(blob_name, reviewed_json)
    except Exception as exc:
        raise FileNotFoundError(
            f"reviewed_documents.json not found locally and not available in blob: {blob_name}"
        ) from exc
    return reviewed_json


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
        logger.info("Deleted existing collection: %s", collection_name)
    except Exception:
        pass

    collection = chroma_client.create_collection(
        name=collection_name,
        metadata={"description": f"Knowledge base: {kb_path.name}"},
    )

    return chroma_client, collection


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _reset_chroma_directory(kb_path: Path) -> None:
    chroma_path = kb_path / "chroma_db"
    if chroma_path.exists():
        shutil.rmtree(chroma_path, ignore_errors=True)


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _is_missing_collections_table_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "no such table: collections" in message or "error getting collection" in message


def _sanitize_chroma_metadata(metadata):
    """Ensure metadata values are JSON-serializable primitives for Chroma."""
    sanitized = {}
    for key, value in (metadata or {}).items():
        if isinstance(value, (dict, list, tuple)):
            sanitized[key] = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[key] = value
        else:
            sanitized[key] = str(value)
    return sanitized


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
    """Index reviewed content into ChromaDB."""
    kb_path = Path(kb_path)
    json_file = _sync_reviewed_json_from_blob(kb_path)

    if not json_file.exists():
        logger.error("File not found: %s", json_file)
        logger.error("Ensure reviewed_documents.json exists before indexing.")
        return

    embedding_provider = os.getenv("EMBEDDING_PROVIDER", os.getenv("LLM_PROVIDER", "vercel"))
    logger.info("Embedding provider: %s", embedding_provider)
    logger.info("Loading JSON from: %s", json_file)

    if json_file.stat().st_size == 0:
        logger.error("Error: %s is empty.", json_file)
        logger.error("Ensure reviewed_documents.json contains valid content.")
        return

    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        logger.exception("Error: invalid JSON in %s (%s).", json_file, exc)
        logger.error("Ensure the input JSON file contains valid content before indexing.")
        return

    source_documents = data.get("documents", [])
    if not source_documents:
        logger.warning("No documents found in JSON file")
        return

    documents = source_documents
    if json_file.name == "reviewed_documents.json":
        normalized_documents = []
        for review_doc in source_documents:
            if not isinstance(review_doc, dict):
                continue
            if not bool(review_doc.get("relevant", False)):
                continue
            key_points = review_doc.get("key_points") or []
            text = str(review_doc.get("text") or "").strip()
            combined_text = "\n".join(str(point).strip() for point in key_points if str(point).strip())
            if not combined_text and text:
                combined_text = text
            if not combined_text:
                continue
            metadata = dict(review_doc.get("metadata") or {})
            metadata.setdefault("filename", review_doc.get("filename") or metadata.get("source_file") or review_doc.get("id") or "reviewed_document")
            metadata.setdefault("source_file", metadata["filename"])
            metadata.setdefault("type", "reviewed_document")
            metadata["relevant"] = True
            metadata["key_points"] = key_points
            metadata["review_reason"] = str(review_doc.get("reason") or "")
            normalized_documents.append({
                "id": review_doc.get("id") or metadata["filename"],
                "text": combined_text,
                "metadata": metadata,
            })
        documents = normalized_documents

    if not documents:
        logger.warning("No relevant reviewed documents found in %s", json_file)
        return

    # Always start from a clean local ChromaDB folder before indexing.
    _reset_chroma_directory(kb_path)

    logger.info("Found %s documents to index", len(documents))

    try:
        _, collection = init_chromadb(kb_path)
    except Exception as exc:
        if _is_missing_collections_table_error(exc):
            logger.warning("ChromaDB schema is missing or corrupted; recreating local database and retrying...")
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

        logger.info("Processing: %s", doc_id)

        chunks = chunk_text(text, chunk_size=1000, overlap=100)
        logger.info("  Created %s chunks", len(chunks))
        total_chunks += len(chunks)

        chunk_embeddings = get_embeddings(chunks)

        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk{i}"
            all_ids.append(chunk_id)
            all_documents.append(chunk)
            all_embeddings.append(chunk_embeddings[i])

            chunk_metadata = {
                    **_sanitize_chroma_metadata(metadata),
                "chunk_index": i,
                "total_chunks": len(chunks),
            }
            all_metadatas.append(chunk_metadata)

            processed_tokens += len(str(chunk).split())
            progress_value = min(processed_tokens, progress_total)
            _write_progress_snapshot("index_chromadb_json", progress_value, progress_total, "tokens")

        logger.info("  Successfully prepared %s", doc_id)
        time.sleep(0.05)

    logger.info("Indexing %s chunks into ChromaDB...", total_chunks)

    batch_size = 1000
    total_batches = (len(all_ids) + batch_size - 1) // batch_size

    for batch_idx in range(total_batches):
        start_idx = batch_idx * batch_size
        end_idx = min((batch_idx + 1) * batch_size, len(all_ids))

        batch_ids = all_ids[start_idx:end_idx]
        batch_documents = all_documents[start_idx:end_idx]
        batch_embeddings = all_embeddings[start_idx:end_idx]
        batch_metadatas = all_metadatas[start_idx:end_idx]

        logger.info("   Batch %s/%s: Adding %s chunks...", batch_idx + 1, total_batches, len(batch_ids))

        try:
            collection.add(
                ids=batch_ids,
                documents=batch_documents,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
            )
        except Exception as exc:
            if _is_missing_collections_table_error(exc):
                logger.warning("ChromaDB schema error detected during indexing; rebuilding local database and retrying...")
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

    logger.info("Successfully indexed %s chunks from %s documents", total_chunks, len(documents))
    logger.info("Collection: %s", collection.name)
    logger.info("Total items: %s", collection.count())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        logger.error("Usage: python index_chromadb_json.py <knowledge_base_path>")
        sys.exit(1)

    kb_path = Path(sys.argv[1])
    logger.info("Starting ChromaDB indexing for: %s", kb_path)
    logger.info("%s", "=" * 60)
    # index_chromadb_json(kb_path=kb_path)
    logger.info("%s", "=" * 60)
    logger.info("Indexing complete! Knowledge base is ready to be queried.")

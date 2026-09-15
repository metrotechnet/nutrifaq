"""
General ChromaDB Indexer
========================
Reads all supported files (PDF, DOCX, TXT, JSON) from a knowledge base's
documents/ folder, extracts text, generates transcripts_chromadb.json,
and indexes everything into ChromaDB.

Works for all projects regardless of their input file formats.

Usage:
    # As a module (from update_chromadb.py):
    from api.index_chromadb import index_project

    index_project("nutria")
    index_project("innovia", embedding_model="text-embedding-3-small")

    # Standalone:
    python -m api.index_chromadb nutria
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

# Locate .env
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
_env = PROJECT_ROOT / ".env"
if _env.exists():
    load_dotenv(dotenv_path=_env, override=True)

OPENAI_API_KEY = os.getenv("AI_GATEWAY_API_KEY") or os.getenv("OPENAI_API_KEY")
OPENAI_API_BASE = os.getenv("AI_GATEWAY_BASE_URL", "https://ai-gateway.vercel.sh/v1")

# Per-project overrides (default: text-embedding-3-large)
_EMBEDDING_MODELS = {
    "innovia": "text-embedding-3-small",
}
_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"


# ─── File readers ────────────────────────────────────────────────────────────

def read_pdf(path):
    import PyPDF2
    with open(path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        return "\n".join(p.extract_text() or "" for p in reader.pages).strip()


def read_docx(path):
    import docx
    doc = docx.Document(path)
    return "\n".join(p.text for p in doc.paragraphs).strip()


def read_txt(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def read_json_as_documents(path):
    """Read a JSON file and return a list of {id, text, metadata} dicts.

    Handles multiple JSON layouts:
      - Array of objects: each object becomes a document
      - Object with "documents" key: standard transcripts_chromadb.json
      - Object with "data" key: dataset format (innovia-style)
      - Single object: treated as one document
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    filename = Path(path).stem
    docs = []

    def obj_to_text(obj):
        """Convert a dict/object to readable text."""
        parts = []
        for k, v in obj.items():
            if k in ("id", "contact"):
                continue
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v if x)
            elif isinstance(v, dict):
                v = json.dumps(v, ensure_ascii=False)
            if v and str(v).strip():
                parts.append(f"{k}: {v}")
        return "\n".join(parts)

    def obj_to_metadata(obj, source_name):
        """Extract all fields from a JSON object as flat metadata."""
        meta = {"source": source_name}
        for k, v in obj.items():
            if k in ("id", "text", "metadata"):
                continue
            if isinstance(v, (str, int, float, bool)):
                meta[k] = v
            elif isinstance(v, list):
                meta[k] = ", ".join(str(x) for x in v if x)
            elif isinstance(v, dict):
                meta[k] = json.dumps(v, ensure_ascii=False)
            elif v is not None:
                meta[k] = str(v)
        return meta

    if isinstance(data, list):
        # Array of objects (e.g. book_dbase_*.json, cctt_docs.json)
        for idx, item in enumerate(data):
            doc_id = item.get("id", f"{filename}_{idx:04d}")
            text = item.get("text") or obj_to_text(item)
            meta = item.get("metadata", {})
            # Merge all source fields into metadata
            meta = {**obj_to_metadata(item, Path(path).name), **meta}
            docs.append({"id": str(doc_id), "text": text, "metadata": meta})

    elif isinstance(data, dict):
        if "documents" in data:
            # transcripts_chromadb.json format
            for item in data["documents"]:
                docs.append({
                    "id": item["id"],
                    "text": item["text"],
                    "metadata": item.get("metadata", {"source": Path(path).name}),
                })
        elif "data" in data:
            # dataset format (e.g. dataset_RD_quebec_pro.json)
            for idx, item in enumerate(data["data"]):
                doc_id = item.get("id", f"{filename}_{idx:04d}")
                text = obj_to_text(item)
                meta = obj_to_metadata(item, Path(path).name)
                docs.append({
                    "id": str(doc_id),
                    "text": text,
                    "metadata": meta,
                })
        else:
            # Single object
            meta = obj_to_metadata(data, Path(path).name)
            docs.append({
                "id": filename,
                "text": obj_to_text(data),
                "metadata": meta,
            })
    return docs


# Map extensions to readers (returns plain text string)
_TEXT_READERS = {
    ".pdf": read_pdf,
    ".docx": read_docx,
    ".txt": read_txt,
}


# ─── Text processing ────────────────────────────────────────────────────────

def chunk_text(text, chunk_size=1000, overlap=100):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        start = end - overlap
    return chunks


# ─── Core pipeline ───────────────────────────────────────────────────────────

def scan_documents(documents_dir):
    """Scan documents/ and return a list of {id, text, metadata} dicts."""
    documents_dir = Path(documents_dir)
    if not documents_dir.exists():
        print(f"⚠️  Documents directory not found: {documents_dir}")
        return []

    all_docs = []
    files = sorted(documents_dir.iterdir())

    for idx, fpath in enumerate(files):
        if fpath.is_dir():
            continue

        ext = fpath.suffix.lower()

        if ext == ".json":
            # JSON files may contain multiple documents
            try:
                json_docs = read_json_as_documents(str(fpath))
                all_docs.extend(json_docs)
                print(f"📄 {fpath.name}: {len(json_docs)} records")
            except Exception as e:
                print(f"⚠️  Failed to read {fpath.name}: {e}")

        elif ext in _TEXT_READERS:
            try:
                text = _TEXT_READERS[ext](str(fpath))
                if not text:
                    print(f"⚠️  No text extracted from {fpath.name}")
                    continue
                reference = fpath.stem
                doc_id = f"doc_{idx:04d}_{reference}"
                all_docs.append({
                    "id": doc_id,
                    "text": text,
                    "metadata": {
                        "source": fpath.name,
                        "reference": reference,
                        "type": ext.lstrip("."),
                        "date": datetime.now().strftime("%Y-%m-%d"),
                    },
                })
                print(f"📄 {fpath.name}: {len(text)} chars")
            except Exception as e:
                print(f"⚠️  Failed to read {fpath.name}: {e}")
        else:
            print(f"⏭️  Skipping unsupported file: {fpath.name}")

    print(f"\n📊 Total documents extracted: {len(all_docs)}")
    return all_docs


def save_transcripts_json(documents, kb_path, project_name):
    """Save documents to transcripts_chromadb.json."""
    output = {
        "knowledge_base": project_name,
        "format": "chromadb",
        "total_documents": len(documents),
        "extracted_at": datetime.now().isoformat(),
        "documents": documents,
    }
    json_path = Path(kb_path) / "transcripts_chromadb.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"📝 Saved {json_path} ({len(documents)} documents)")
    return json_path


def index_into_chromadb(documents, kb_path, project_name, collection_name="gdrive_documents", embedding_model=None):
    """Chunk documents and index them into ChromaDB."""
    kb_path = Path(kb_path)
    chroma_path = str(kb_path / "chroma_db")
    os.makedirs(chroma_path, exist_ok=True)

    if not embedding_model:
        embedding_model = _EMBEDDING_MODELS.get(project_name, _DEFAULT_EMBEDDING_MODEL)

    ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=OPENAI_API_KEY, model_name=embedding_model,
        api_base=OPENAI_API_BASE,
    )

    client = chromadb.PersistentClient(
        path=chroma_path,
        settings=Settings(anonymized_telemetry=False, allow_reset=False),
    )

    # Reset collection
    try:
        client.delete_collection(name=collection_name)
        print(f"♻️  Deleted existing collection: {collection_name}")
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={"description": f"Knowledge base: {project_name}"},
    )

    # Chunk and prepare
    all_ids = []
    all_documents = []
    all_metadatas = []

    for doc in documents:
        doc_id = doc["id"]
        text = doc["text"]
        metadata = doc.get("metadata", {})

        if not text or not text.strip():
            continue

        chunks = chunk_text(text, chunk_size=1000, overlap=100)

        for i, chunk in enumerate(chunks):
            all_ids.append(f"{doc_id}_chunk{i}")
            all_documents.append(chunk)
            # Clean metadata: only keep string/int/float values
            clean_meta = {}
            for k, v in metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    clean_meta[k] = v
            clean_meta["chunk_index"] = i
            clean_meta["total_chunks"] = len(chunks)
            all_metadatas.append(clean_meta)

    # Batch insert (let ChromaDB EF handle embeddings)
    BATCH_SIZE = 500
    total_batches = (len(all_ids) + BATCH_SIZE - 1) // BATCH_SIZE

    print(f"\n📊 Indexing {len(all_ids)} chunks into ChromaDB...")

    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(all_ids))
        print(f"   Batch {batch_idx + 1}/{total_batches}: {end - start} chunks...")

        collection.add(
            ids=all_ids[start:end],
            documents=all_documents[start:end],
            metadatas=all_metadatas[start:end],
        )

    print(f"\n✅ Indexed {len(all_ids)} chunks from {len(documents)} documents")
    print(f"📦 Collection: {collection.name} ({collection.count()} items)")
    return True


def index_project(project_name, collection_name="gdrive_documents", embedding_model=None):
    """Full pipeline: scan documents → save JSON → index ChromaDB.

    Args:
        project_name: Name of the knowledge base folder.
        collection_name: ChromaDB collection name.
        embedding_model: Override embedding model (default per-project config).

    Returns:
        dict with result info.
    """
    kb_path = PROJECT_ROOT / "knowledge-base" / project_name
    documents_dir = kb_path / "documents"

    print(f"{'=' * 60}")
    print(f"🚀 Indexing project: {project_name}")
    print(f"   KB path: {kb_path}")
    print(f"   Documents: {documents_dir}")
    print(f"{'=' * 60}\n")

    # Step 1: Scan and extract text from all files
    documents = scan_documents(documents_dir)
    if not documents:
        print("❌ No documents found to index")
        return {"indexed": False, "documents": 0, "chunks": 0}

    # Step 2: Save transcripts_chromadb.json
    save_transcripts_json(documents, kb_path, project_name)

    # Step 3: Index into ChromaDB
    indexed = index_into_chromadb(
        documents, kb_path, project_name,
        collection_name=collection_name,
        embedding_model=embedding_model,
    )

    return {"indexed": indexed, "documents": len(documents)}


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m api.index_chromadb <project_name> [collection_name]")
        sys.exit(1)

    proj = sys.argv[1]
    col = sys.argv[2] if len(sys.argv) > 2 else "gdrive_documents"
    result = index_project(proj, collection_name=col)
    if result["indexed"]:
        print(f"\n✅ Done! {result['documents']} documents indexed.")
    else:
        print("\n❌ Indexing failed.")
        sys.exit(1)

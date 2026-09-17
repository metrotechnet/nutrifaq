"""
Index ChromaDB from JSON
=========================
This script indexes the ChromaDB-compatible JSON format into ChromaDB.
It reads the transcripts_chromadb.json file and creates vector embeddings
for efficient semantic search.

Usage:
    python core/index_chromadb_json.py [knowledge_base_path]

Example:
    python core/index_chromadb_json.py /path/to/id-agent/knowledge-base/agent
"""

import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from openai import OpenAI


# Get main root directory (where .env is located)
MAIN_ROOT = Path.cwd()
while not (MAIN_ROOT / '.env').exists() and MAIN_ROOT.parent != MAIN_ROOT:
    MAIN_ROOT = MAIN_ROOT.parent

# Load environment variables
env_path = MAIN_ROOT / '.env'
load_dotenv(dotenv_path=env_path, override=True)

# Initialize Vercel AI Gateway client (OpenAI-compatible)
client = OpenAI(
    api_key=os.getenv("AI_GATEWAY_API_KEY"),
    base_url="https://ai-gateway.vercel.sh/v1"
)


def get_embeddings(texts):
    """Get embeddings from OpenAI"""
    if isinstance(texts, str):
        texts = [texts]
    
    # Process in batches to avoid rate limits
    batch_size = 100
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = client.embeddings.create(model="text-embedding-3-large", input=batch)
        all_embeddings.extend([e.embedding for e in resp.data])
    
    return all_embeddings


def init_chromadb(kb_path):
    """Initialize ChromaDB client for a specific knowledge base"""
    kb_path = Path(kb_path)
    chroma_path = str(kb_path / "chroma_db")
    
    # Create directories if they don't exist
    os.makedirs(chroma_path, exist_ok=True)

    chroma_client = chromadb.PersistentClient(
        path=chroma_path,
        settings=Settings(
            anonymized_telemetry=False,
            allow_reset=False
        )
    )
    
    collection_name = "gdrive_documents"
    
    # OpenAI embedding function for consistent embedding across build and update
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=OPENAI_API_KEY, model_name="text-embedding-3-large"
    )
    
    # Reset collection if it exists
    try:
        chroma_client.delete_collection(name=collection_name)
        print(f"\u267b\ufe0f  Deleted existing collection: {collection_name}")
    except:
        pass
    
    collection = chroma_client.create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={"description": f"Knowledge base: {kb_path.name}"}
    )
    
    return chroma_client, collection


def chunk_text(text, chunk_size=1000, overlap=100):
    """Split text into overlapping chunks"""
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
    """
    Index ChromaDB-compatible JSON into ChromaDB
    
    Args:
        kb_path: Path to the knowledge base directory
    """
    kb_path = Path(kb_path)
    json_file = kb_path / "transcripts_chromadb.json"
    
    if not json_file.exists():
        print(f"❌ File not found: {json_file}")
        print(f"   Ensure transcripts_chromadb.json was created first")
        return
    
    # Load JSON data
    print(f"📖 Loading JSON from: {json_file}")
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    documents = data.get("documents", [])
    if not documents:
        print("❌ No documents found in JSON file")
        return
    
    print(f"Found {len(documents)} documents to index\n")
    
    # Initialize ChromaDB
    chroma_client, collection = init_chromadb(kb_path)
    
    all_ids = []
    all_embeddings = []
    all_documents = []
    all_metadatas = []
    
    total_chunks = 0
    
    for doc in documents:
        doc_id = doc["id"]
        text = doc["text"]
        metadata = doc["metadata"]
        
        print(f"Processing: {doc_id}")
        
        # Chunk the text
        chunks = chunk_text(text, chunk_size=1000, overlap=100)
        print(f"  Created {len(chunks)} chunks")
        total_chunks += len(chunks)
        
        # Get embeddings for all chunks
        embeddings = get_embeddings(chunks)
        
        # Prepare data for ChromaDB
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_id = f"{doc_id}_chunk{i}"
            all_ids.append(chunk_id)
            all_embeddings.append(embedding)
            all_documents.append(chunk)
            
            # Add chunk index to metadata
            chunk_metadata = {
                **metadata,
                "chunk_index": i,
                "total_chunks": len(chunks)
            }
            all_metadatas.append(chunk_metadata)
        
        print(f"  ✅ Successfully prepared {doc_id}")
    
    # Add all documents to ChromaDB in batches to avoid max batch size errors
    print(f"\n📊 Indexing {total_chunks} chunks into ChromaDB...")
    
    BATCH_SIZE = 1000  # Safe batch size for ChromaDB
    total_batches = (len(all_ids) + BATCH_SIZE - 1) // BATCH_SIZE
    
    for batch_idx in range(total_batches):
        start_idx = batch_idx * BATCH_SIZE
        end_idx = min((batch_idx + 1) * BATCH_SIZE, len(all_ids))
        
        batch_ids = all_ids[start_idx:end_idx]
        batch_documents = all_documents[start_idx:end_idx]
        batch_metadatas = all_metadatas[start_idx:end_idx]
        
        print(f"   Batch {batch_idx + 1}/{total_batches}: Adding {len(batch_ids)} chunks...")
        
        collection.add(
            ids=batch_ids,
            documents=batch_documents,
            metadatas=batch_metadatas
        )
    
    print(f"\n✅ Successfully indexed {total_chunks} chunks from {len(documents)} documents!")
    print(f"📦 Collection: {collection.name}")
    print(f"📈 Total items: {collection.count()}")


if __name__ == "__main__":
    # Get knowledge base path from command line
    
    kb_path = "."
    
    print(f"Starting ChromaDB indexing for: {kb_path}\n")
    print("=" * 60)
    index_chromadb_json(kb_path=kb_path)
    print("=" * 60)
    print(f"\n✅ Indexing complete! Knowledge base is ready to be queried.")

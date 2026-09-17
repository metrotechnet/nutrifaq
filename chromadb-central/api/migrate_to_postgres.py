"""
Migration script: Move data from ChromaDB to PostgreSQL + pgvector.
Handles schema creation, data migration, and indexing.
"""
import os
import json
import tempfile
import base64
import hashlib
import hmac
from datetime import datetime, timezone
from urllib.parse import quote
from typing import Dict, List, Tuple, Optional
from api.postgres_db import get_postgres_connection, _postgres_setting
import chromadb
from chromadb.config import Settings


def _blob_setting(name, default=""):
    value = os.getenv(name, default)
    if value is None:
        return default
    return str(value).strip()


def _get_azure_blob_client():
    storage_account = _blob_setting("AZURE_STORAGE_ACCOUNT")
    container_name = _blob_setting("AZURE_STORAGE_CONTAINER") or _blob_setting("AZURE_BLOB_CONTAINER")
    storage_key = _blob_setting("AZURE_STORAGE_KEY") or _blob_setting("AZURE_STORAGE_ACCOUNT_KEY")

    if not storage_account or not container_name:
        return None, None, None

    try:
        from azure.storage.blob import BlobServiceClient
    except ImportError:
        return None, storage_account, container_name

    if storage_key:
        service_client = BlobServiceClient(
            account_url=f"https://{storage_account}.blob.core.windows.net",
            credential=storage_key,
        )
    else:
        service_client = BlobServiceClient(
            account_url=f"https://{storage_account}.blob.core.windows.net",
        )

    return service_client, storage_account, container_name


def _azure_rfc1123_now():
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def _azure_shared_key_headers(method: str, account: str, resource_path: str, key: str, query_params=None, content_length: str = ""):
    query_params = query_params or {}
    x_ms_date = _azure_rfc1123_now()
    x_ms_version = "2021-12-02"

    canonicalized_headers = f"x-ms-date:{x_ms_date}\nx-ms-version:{x_ms_version}\n"
    canonicalized_resource = f"/{account}{resource_path}"
    if query_params:
        for param_name in sorted(query_params):
            canonicalized_resource += f"\n{param_name.lower()}:{query_params[param_name]}"

    string_to_sign = (
        f"{method}\n"
        f"\n"
        f"\n"
        f"{content_length}\n"
        f"\n"
        f"\n"
        f"\n"
        f"\n"
        f"\n"
        f"\n"
        f"\n"
        f"\n"
        f"{canonicalized_headers}"
        f"{canonicalized_resource}"
    )

    decoded_key = base64.b64decode(key)
    signature = base64.b64encode(
        hmac.new(decoded_key, string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")

    return {
        "x-ms-date": x_ms_date,
        "x-ms-version": x_ms_version,
        "Authorization": f"SharedKey {account}:{signature}",
    }


def _blob_list_via_rest(storage_account: str, container_name: str, storage_key: str, prefix: str):
    import urllib.request
    from urllib.parse import urlencode

    query_params = {
        "restype": "container",
        "comp": "list",
        "prefix": prefix,
    }
    resource_path = f"/{container_name}"
    headers = _azure_shared_key_headers("GET", storage_account, resource_path, storage_key, query_params=query_params)

    url = f"https://{storage_account}.blob.core.windows.net/{container_name}?{urlencode(query_params)}"
    request = urllib.request.Request(url, method="GET")
    for header_name, header_value in headers.items():
        request.add_header(header_name, header_value)

    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read().decode("utf-8")

    return payload


def _download_blob_via_rest(storage_account: str, container_name: str, storage_key: str, blob_name: str, local_path: str):
    import urllib.request

    resource_path = f"/{container_name}/{blob_name}"
    headers = _azure_shared_key_headers("GET", storage_account, resource_path, storage_key)
    url = f"https://{storage_account}.blob.core.windows.net/{container_name}/{quote(blob_name)}"

    request = urllib.request.Request(url, method="GET")
    for header_name, header_value in headers.items():
        request.add_header(header_name, header_value)

    with urllib.request.urlopen(request, timeout=120) as response, open(local_path, "wb") as file_handle:
        file_handle.write(response.read())


def _parse_blob_list_xml(blob_xml: str):
    import xml.etree.ElementTree as ET

    root = ET.fromstring(blob_xml)
    namespaces = {"b": "http://schemas.microsoft.com/azure/storage/2009/09"}
    names = []
    for blob in root.findall(".//b:Blob", namespaces):
        name_element = blob.find("b:Name", namespaces)
        if name_element is not None and name_element.text:
            names.append(name_element.text)
    return names


def _download_chroma_db_from_azure_blob_rest(project_name: str):
    storage_account = _blob_setting("AZURE_STORAGE_ACCOUNT")
    container_name = _blob_setting("AZURE_STORAGE_CONTAINER") or _blob_setting("AZURE_BLOB_CONTAINER")
    storage_key = _blob_setting("AZURE_STORAGE_KEY") or _blob_setting("AZURE_STORAGE_ACCOUNT_KEY")

    if not storage_account or not container_name or not storage_key:
        return None

    prefix = f"knowledge-base/{project_name}/chroma_db/"
    temp_root = tempfile.mkdtemp(prefix="nutrifaq-chroma-")
    local_dir = os.path.join(temp_root, project_name, "chroma_db")
    os.makedirs(local_dir, exist_ok=True)

    try:
        blob_xml = _blob_list_via_rest(storage_account, container_name, storage_key, prefix)
        blob_names = _parse_blob_list_xml(blob_xml)
    except Exception as exc:
        print(f"[Azure Blob REST] Failed to list blobs for {project_name}: {exc}")
        return None

    if not blob_names:
        return None

    count = 0
    for blob_name in blob_names:
        if blob_name.endswith("/"):
            continue
        relative_path = blob_name[len(prefix):]
        local_path = os.path.join(local_dir, relative_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        try:
            _download_blob_via_rest(storage_account, container_name, storage_key, blob_name, local_path)
            count += 1
        except Exception as exc:
            print(f"[Azure Blob REST] Failed to download {blob_name}: {exc}")

    print(f"[Azure Blob REST] Downloaded {count} files for {project_name}/chroma_db from {storage_account}/{container_name}")
    return local_dir


def _download_chroma_db_from_azure_blob(project_name: str):
    service_client, storage_account, container_name = _get_azure_blob_client()
    if service_client is None or not storage_account or not container_name:
        return None

    container_client = service_client.get_container_client(container_name)
    prefix = f"knowledge-base/{project_name}/chroma_db/"
    temp_root = tempfile.mkdtemp(prefix="nutrifaq-chroma-")
    local_dir = os.path.join(temp_root, project_name, "chroma_db")
    os.makedirs(local_dir, exist_ok=True)

    blobs = list(container_client.list_blobs(name_starts_with=prefix))
    if not blobs:
        return None

    count = 0
    for blob in blobs:
        if blob.name.endswith("/"):
            continue
        relative_path = blob.name[len(prefix):]
        local_path = os.path.join(local_dir, relative_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as file_handle:
            download_stream = container_client.download_blob(blob.name)
            file_handle.write(download_stream.readall())
        count += 1

    print(f"[Azure Blob] Downloaded {count} files for {project_name}/chroma_db from {storage_account}/{container_name}")
    return local_dir


def _get_chroma_client(project_name: str):
    """Get a ChromaDB client for a specific project."""
    kb_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "knowledge-base",
        project_name,
        "chroma_db"
    )
    if not os.path.exists(kb_path):
        kb_path = _download_chroma_db_from_azure_blob(project_name) or _download_chroma_db_from_azure_blob_rest(project_name)
        if not kb_path:
            return None
    try:
        return chromadb.PersistentClient(
            path=kb_path,
            settings=Settings(anonymized_telemetry=False, allow_reset=False)
        )
    except Exception as e:
        print(f"[Chroma] Failed to initialize client for {project_name}: {e}")
        return None


def create_vector_table(project_name: str, collection_name: str) -> Tuple[bool, str]:
    """Create a pgvector table for a specific collection."""
    try:
        conn = get_postgres_connection()
        table_name = f"{project_name}_{collection_name}".lower().replace("-", "_")
        
        with conn.cursor() as cur:
            # Enable pgvector extension
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            
            # Check if table already exists
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = %s",
                (table_name,)
            )
            if cur.fetchone():
                return True, f"Table {table_name} already exists"
            
            # Create the table with pgvector column
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS "{table_name}" (
                id SERIAL PRIMARY KEY,
                uuid TEXT UNIQUE,
                content TEXT NOT NULL,
                embedding vector(3072),
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
            cur.execute(create_table_sql)
            
            # Create indexes for performance. Azure Database for PostgreSQL currently rejects IVFFlat
            # for embeddings above 2000 dimensions, so HNSW is used instead for the 3072-dim files
            # produced by the current pipeline.
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_embedding ON \"{table_name}\" USING hnsw (embedding vector_cosine_ops)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_uuid ON \"{table_name}\" (uuid)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_content ON \"{table_name}\" USING GIN (to_tsvector('english', content))")
            
        conn.commit()
        conn.close()
        return True, f"Table {table_name} created successfully"
    except Exception as e:
        return False, f"Error creating table: {str(e)}"


def migrate_collection_data(project_name: str, collection_name: str, batch_size: int = 100) -> Tuple[int, str]:
    """Migrate data from ChromaDB collection to PostgreSQL."""
    try:
        chroma_client = _get_chroma_client(project_name)
        if chroma_client is None:
            return 0, f"ChromaDB not found for project {project_name}"
        
        # Get the collection from Chroma
        try:
            chroma_collection = chroma_client.get_collection(name=collection_name)
        except Exception as e:
            return 0, f"Collection {collection_name} not found in ChromaDB: {str(e)}"
        
        # Get PostgreSQL connection
        conn = get_postgres_connection()
        table_name = f"{project_name}_{collection_name}".lower().replace("-", "_")
        
        # Get all documents from Chroma
        try:
            # Chroma get() without where clause retrieves all
            results = chroma_collection.get(
                include=["embeddings", "documents", "metadatas", "ids"]
            )
        except Exception as e:
            conn.close()
            return 0, f"Failed to retrieve data from ChromaDB: {str(e)}"
        
        ids = results.get("ids", [])
        documents = results.get("documents", [])
        embeddings = results.get("embeddings", [])
        metadatas = results.get("metadatas", [])
        
        if not ids:
            conn.close()
            return 0, "No documents found in ChromaDB collection"
        
        # Prepare batch insert
        migrated_count = 0
        skipped_count = 0
        
        with conn.cursor() as cur:
            for i in range(0, len(ids), batch_size):
                batch_ids = ids[i:i+batch_size]
                batch_docs = documents[i:i+batch_size]
                batch_embeddings = embeddings[i:i+batch_size] if embeddings else [None] * len(batch_ids)
                batch_metadata = metadatas[i:i+batch_size] if metadatas else [{}] * len(batch_ids)
                
                for doc_id, content, embedding, meta in zip(batch_ids, batch_docs, batch_embeddings, batch_metadata):
                    try:
                        # Handle metadata
                        meta_json = json.dumps(meta) if meta else None
                        
                        # Handle embedding (must be list for pgvector)
                        if embedding is None:
                            embedding = [0.0] * 3072  # Default zero vector
                        elif hasattr(embedding, 'tolist'):
                            embedding = embedding.tolist()
                        
                        # Insert with ON CONFLICT to handle duplicates
                        cur.execute(
                            f"""
                            INSERT INTO "{table_name}" (uuid, content, embedding, metadata)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (uuid) DO UPDATE
                            SET content = EXCLUDED.content, embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata, updated_at = CURRENT_TIMESTAMP
                            """,
                            (str(doc_id), str(content), embedding, meta_json)
                        )
                        migrated_count += 1
                    except Exception as e:
                        print(f"[Migrate] Error inserting {doc_id}: {str(e)}")
                        skipped_count += 1
                
                # Commit in batches
                conn.commit()
        
        conn.close()
        return migrated_count, f"Migrated {migrated_count} documents ({skipped_count} skipped)"
    except Exception as e:
        return 0, f"Migration failed: {str(e)}"


def get_migration_status() -> Dict:
    """Get the current status of migration."""
    try:
        conn = get_postgres_connection()
    except Exception as e:
        return {
            "postgres_available": False,
            "error": str(e),
            "tables": [],
            "total_documents": 0
        }
    
    status = {
        "postgres_available": True,
        "tables": [],
        "total_documents": 0
    }
    
    try:
        with conn.cursor() as cur:
            # Get all custom tables (not system tables)
            cur.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = current_schema() 
                AND table_name NOT LIKE 'pg_%'
                ORDER BY table_name
            """)
            tables = cur.fetchall()
            
            for (table_name,) in tables:
                # Get document count and vector status for each table
                cur.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                count = cur.fetchone()[0]
                
                cur.execute(f"""
                    SELECT COUNT(*) FROM "{table_name}" WHERE embedding IS NOT NULL
                """)
                vector_count = cur.fetchone()[0]
                
                status["tables"].append({
                    "name": table_name,
                    "document_count": count,
                    "vectors_indexed": vector_count,
                    "missing_vectors": count - vector_count
                })
                status["total_documents"] += count
    except Exception as e:
        status["error"] = str(e)
    finally:
        conn.close()
    
    return status


def list_chromadb_projects() -> Dict[str, List[str]]:
    """List all available ChromaDB projects and their collections."""
    kb_root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "knowledge-base"
    )
    
    projects = {}
    if os.path.isdir(kb_root):
        for project_dir in os.listdir(kb_root):
            chroma_path = os.path.join(kb_root, project_dir, "chroma_db")
            if not os.path.isdir(chroma_path):
                continue
            
            try:
                client = _get_chroma_client(project_dir)
                if client is None:
                    continue
                
                collections = [c.name for c in client.list_collections()]
                projects[project_dir] = collections
            except Exception as e:
                print(f"[List] Error reading project {project_dir}: {e}")

    if projects:
        return projects

    service_client, storage_account, container_name = _get_azure_blob_client()
    if service_client is None and (not storage_account or not container_name):
        return projects

    try:
        prefixes = set()

        if service_client is not None:
            container_client = service_client.get_container_client(container_name)
            for blob in container_client.list_blobs(name_starts_with="knowledge-base/"):
                parts = blob.name.split("/")
                if len(parts) >= 3 and parts[0] == "knowledge-base":
                    prefixes.add(parts[1])
        else:
            blob_key = _blob_setting("AZURE_STORAGE_KEY") or _blob_setting("AZURE_STORAGE_ACCOUNT_KEY")
            if not blob_key:
                return projects

            import urllib.request
            from urllib.parse import urlencode

            query_params = {"restype": "container", "comp": "list", "prefix": "knowledge-base/"}
            headers = _azure_shared_key_headers("GET", storage_account, f"/{container_name}", blob_key, query_params=query_params)
            url = f"https://{storage_account}.blob.core.windows.net/{container_name}?{urlencode(query_params)}"
            request = urllib.request.Request(url, method="GET")
            for header_name, header_value in headers.items():
                request.add_header(header_name, header_value)

            with urllib.request.urlopen(request, timeout=60) as response:
                blob_xml = response.read().decode("utf-8")

            for blob_name in _parse_blob_list_xml(blob_xml):
                parts = blob_name.split("/")
                if len(parts) >= 3 and parts[0] == "knowledge-base":
                    prefixes.add(parts[1])

        for project_name in sorted(prefixes):
            downloaded_path = _download_chroma_db_from_azure_blob(project_name)
            if not downloaded_path:
                downloaded_path = _download_chroma_db_from_azure_blob_rest(project_name)
            if not downloaded_path:
                continue
            try:
                client = chromadb.PersistentClient(
                    path=downloaded_path,
                    settings=Settings(anonymized_telemetry=False, allow_reset=False)
                )
                projects[project_name] = [c.name for c in client.list_collections()]
            except Exception as e:
                print(f"[List] Error reading Azure Blob project {project_name}: {e}")
    except Exception as e:
        print(f"[List] Failed to list projects from Azure Blob Storage: {e}")
    
    return projects


def migrate_all_projects() -> Dict:
    """Migrate all ChromaDB projects to PostgreSQL."""
    projects = list_chromadb_projects()
    results = {}
    
    for project_name, collections in projects.items():
        results[project_name] = {}
        for collection_name in collections:
            # Create table
            table_created, msg = create_vector_table(project_name, collection_name)
            print(f"[Migrate] {project_name}/{collection_name}: {msg}")
            
            if not table_created:
                results[project_name][collection_name] = {
                    "status": "failed",
                    "message": msg
                }
                continue
            
            # Migrate data
            migrated, msg = migrate_collection_data(project_name, collection_name)
            results[project_name][collection_name] = {
                "status": "success" if migrated > 0 else "no_data",
                "documents_migrated": migrated,
                "message": msg
            }
    
    return results


if __name__ == "__main__":
    print("[Migrate] Starting full migration...")
    results = migrate_all_projects()
    print(json.dumps(results, indent=2))
    
    print("\n[Migrate] Final status:")
    status = get_migration_status()
    print(json.dumps(status, indent=2))

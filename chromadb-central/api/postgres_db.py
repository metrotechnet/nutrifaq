import json
import os
import re
from urllib.parse import quote_plus


def _postgres_setting(name, default=""):
    value = os.getenv(name, default)
    if value is None:
        return default
    return str(value).strip()


def get_postgres_dsn():
    """Build the Postgres DSN for Azure Database for PostgreSQL Flexible Server."""
    configured_url = os.getenv("POSTGRES_DATABASE_URL") or os.getenv("DATABASE_URL")
    if configured_url:
        return configured_url.rstrip("/")

    host = _postgres_setting("POSTGRES_HOST")
    port = _postgres_setting("POSTGRES_PORT", "5432") or "5432"
    db = _postgres_setting("POSTGRES_DB")
    user = _postgres_setting("POSTGRES_USER")
    password = _postgres_setting("POSTGRES_PASSWORD")
    sslmode = _postgres_setting("POSTGRES_SSLMODE", "require") or "require"

    if not host or not db:
        raise RuntimeError("POSTGRES_HOST and POSTGRES_DB must be configured before connecting to PostgreSQL.")
    if not user:
        raise RuntimeError("POSTGRES_USER must be configured before connecting to PostgreSQL.")
    if not password:
        raise RuntimeError("POSTGRES_PASSWORD must be configured before connecting to PostgreSQL.")

    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}@"
        f"{host}:{port}/{db}?sslmode={sslmode}"
    )


def get_postgres_connection():
    """Open a PostgreSQL connection using the configured Azure server."""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is not installed. Install it with: pip install 'psycopg[binary]' ") from exc

    dsn = get_postgres_dsn()
    return psycopg.connect(dsn, connect_timeout=10)


def test_postgres_connection():
    """Validate the configured connection and return a health payload."""
    if not (os.getenv("POSTGRES_HOST") or os.getenv("POSTGRES_DATABASE_URL") or os.getenv("DATABASE_URL")):
        return {
            "status": "not_configured",
            "details": "POSTGRES_HOST or DATABASE_URL is not configured.",
        }

    conn = None
    try:
        conn = get_postgres_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            result = cur.fetchone()
        return {
            "status": "ok" if result == (1,) else "unknown",
            "host": _postgres_setting("POSTGRES_HOST", "configured"),
            "database": _postgres_setting("POSTGRES_DB", "configured"),
            "details": "PostgreSQL connection verified.",
        }
    except Exception as exc:
        return {
            "status": "error",
            "details": str(exc),
            "host": _postgres_setting("POSTGRES_HOST", "unknown"),
            "database": _postgres_setting("POSTGRES_DB", "unknown"),
        }
    finally:
        if conn is not None:
            conn.close()


def _to_identifier(name):
    return '"' + str(name).replace('"', '""') + '"'


def _table_exists(conn, table_name):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = %s",
            (table_name,),
        )
        return cur.fetchone() is not None


def _column_names(conn, table_name):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = %s",
            (table_name,),
        )
        return {row[0].lower() for row in cur.fetchall()}


def _resolve_vector_table(conn, project_name, collection_name):
    project_name = (project_name or "").strip()
    collection_name = (collection_name or "").strip()

    candidates = [
        f"{project_name}_{collection_name}",
        f"{project_name}_{collection_name}_vectors",
        f"{project_name}_{collection_name}_documents",
        collection_name,
        f"{project_name}_documents",
        f"{project_name}_vectors",
        "documents",
        "document_vectors",
        "vector_documents",
    ]

    seen = set()
    for candidate in candidates:
        candidate = candidate.lower()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if not _table_exists(conn, candidate):
            continue
        columns = _column_names(conn, candidate)
        if any(col in columns for col in ("embedding", "vector", "embedding_vector")) and any(
            col in columns for col in ("content", "document", "text", "body", "chunk")
        ):
            return candidate, columns
    return None, set()


def query_pgvector(project_name, collection_name, query):
    """Query PostgreSQL + pgvector using the same payload contract as the Chroma layer."""
    if not isinstance(query, dict):
        return {"error": "Invalid vector search payload.", "details": "Expected a dict with query_embedding or query_embeddings."}

    query_embedding = query.get("query_embedding")
    if query_embedding is None:
        query_embedding = query.get("query_embeddings")
        if isinstance(query_embedding, list) and query_embedding:
            query_embedding = query_embedding[0]

    if query_embedding is None:
        return {"error": "Invalid vector search payload.", "details": "Missing required field: query_embedding."}

    if hasattr(query_embedding, "tolist"):
        query_embedding = query_embedding.tolist()

    if not isinstance(query_embedding, (list, tuple)) or not query_embedding:
        return {"error": "Invalid vector search payload.", "details": "query_embedding must be a non-empty list-like vector."}

    try:
        conn = get_postgres_connection()
    except Exception as exc:
        return {"error": "PostgreSQL connection is not available.", "details": str(exc)}

    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

            table_name, columns = _resolve_vector_table(conn, project_name, collection_name)
            if not table_name:
                return {"error": "No pgvector table found.", "details": f"Checked project={project_name} collection={collection_name}"}

            vector_column = next((name for name in ("embedding", "vector", "embedding_vector") if name in columns), None)
            id_column = next((name for name in ("id", "uuid", "document_id", "row_id") if name in columns), "id")
            content_column = next((name for name in ("content", "document", "text", "body", "chunk", "page_content") if name in columns), "content")
            metadata_column = next((name for name in ("metadata", "metadatas", "json", "payload", "source_metadata") if name in columns), None)

            if not vector_column:
                return {"error": "No pgvector column found.", "details": f"Table {table_name} does not contain an embedding vector column."}

            limit = max(1, min(int(query.get("n_results", 5)), 25))
            metadata_select = _to_identifier(metadata_column) if metadata_column else "NULL"
            sql = (
                f"SELECT {_to_identifier(id_column)}, {_to_identifier(content_column)}, {metadata_select}, {_to_identifier(vector_column)} "
                f"FROM {_to_identifier(table_name)} "
                f"ORDER BY {_to_identifier(vector_column)} <-> %s LIMIT %s"
            )
            cur.execute(sql, (query_embedding, limit))
            rows = cur.fetchall()

            documents = []
            metadatas = []
            ids = []
            distances = []

            for row in rows:
                item_id, content, meta, _ = row
                documents.append(content)
                ids.append(str(item_id))

                if meta is None:
                    parsed_meta = {}
                elif isinstance(meta, dict):
                    parsed_meta = meta
                else:
                    try:
                        parsed_meta = json.loads(meta)
                    except Exception:
                        try:
                            parsed_meta = {"value": meta}
                        except Exception:
                            parsed_meta = {}
                metadatas.append(parsed_meta)
                distances.append(0.0)

            return {
                "documents": [documents],
                "metadatas": [metadatas],
                "ids": [ids],
                "distances": [distances],
            }
    except Exception as exc:
        return {"error": "PostgreSQL vector query failed.", "details": str(exc)}
    finally:
        conn.close()

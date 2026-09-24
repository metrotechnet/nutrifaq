import os
import json
import re
from typing import Any
from pathlib import Path
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings
from api.services.refusal_engine import validate_user_query
from api.services.llm_service import (
    build_prompt_from_template,
    create_chat_completion_stream,
    create_embedding,
    get_gateway_client,
)
from api.services.blob_storage_service import (
    get_blob_container_name,
    get_blob_prefix,
    get_blob_properties,
)

# API and repository roots
API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
load_dotenv(dotenv_path=REPO_ROOT / '.env')

DEFAULT_PROJECT_NAME = os.getenv("KNOWLEDGE_BASE_NAME", "nutrifaq")
DEFAULT_COLLECTION_NAME = os.getenv("DEFAULT_COLLECTION_NAME", "nutrifaq-collection")

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_ACCOUNT = os.getenv("AZURE_STORAGE_ACCOUNT")
AZURE_STORAGE_KEY = os.getenv("AZURE_STORAGE_KEY")
AZURE_STORAGE_SAS_TOKEN = os.getenv("AZURE_STORAGE_SAS_TOKEN")

AZURE_STORAGE_CONTAINER = get_blob_container_name()

AZURE_BLOB_PREFIX = get_blob_prefix()
LOCAL_BLOB_CACHE_ROOT = REPO_ROOT / ".cache" / AZURE_BLOB_PREFIX / "chroma_db"
LOCAL_BLOB_MARKER_FILE = LOCAL_BLOB_CACHE_ROOT / ".blob_signature"
ROOT_BLOB_CACHE_ROOT = REPO_ROOT / "nutrifaq-dbase" / "chroma_db"

_CHROMA_CLIENT_CACHE: dict[str, Any] = {}
_CHROMA_COLLECTION_CACHE: dict[tuple[str, str], Any] = {}
_CHROMA_SIGNATURE_CACHE: str | None = None


def _repo_chroma_path() -> Path:
    return REPO_ROOT / "nutrifaq-dbase" / "chroma_db"


def _resolve_local_chroma_root(
    root_folder: str | None = None,
    chroma_db_path: str | None = None,
) -> Path:
    if chroma_db_path:
        candidate = Path(chroma_db_path)
        return candidate if candidate.is_absolute() else (REPO_ROOT / candidate)

    folder = (root_folder or "nutrifaq-dbase").strip("/")
    return REPO_ROOT / folder / "chroma_db"


def get_debug_local_kb_root_folder() -> str:
    """Return the local debug KB root folder name used by /query_debug."""
    return os.getenv("AZURE_KB_DEBUG_LOCAL_ROOT", "nutrifaq-dbase-main").strip("/")


def _remote_chroma_signature() -> str:
    return get_blob_properties(f"{AZURE_BLOB_PREFIX}/chroma_db/chroma.sqlite3").etag


def _read_local_signature() -> str | None:
    if not LOCAL_BLOB_MARKER_FILE.exists():
        return None
    try:
        return LOCAL_BLOB_MARKER_FILE.read_text(encoding="utf-8").strip() or None
    except Exception:
        return None


def _write_local_signature(signature: str) -> None:
    LOCAL_BLOB_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    LOCAL_BLOB_MARKER_FILE.write_text(signature, encoding="utf-8")


def _sync_chroma_from_blob(force: bool = False) -> Path:
    global _CHROMA_SIGNATURE_CACHE

    if not (AZURE_STORAGE_CONNECTION_STRING or (AZURE_STORAGE_ACCOUNT and AZURE_STORAGE_KEY)):
        raise RuntimeError(
            "Azure Blob Storage configuration is required for ChromaDB access."
        )

    if ROOT_BLOB_CACHE_ROOT.exists() and not force:
        return ROOT_BLOB_CACHE_ROOT

    raise RuntimeError(
        f"ChromaDB has not been loaded into {ROOT_BLOB_CACHE_ROOT}. It must be populated at startup."
    )


def _local_chroma_client(
    project_name: str,
    root_folder: str | None = None,
    chroma_db_path: str | None = None,
):
    kb_path = _resolve_local_chroma_root(root_folder, chroma_db_path)
    if not kb_path.exists():
        raise FileNotFoundError(
            f"Local ChromaDB directory not found: {kb_path}. Blob database was not loaded at startup."
        )

    cache_key = str(kb_path)
    if cache_key in _CHROMA_CLIENT_CACHE:
        return _CHROMA_CLIENT_CACHE[cache_key]

    client = chromadb.PersistentClient(
        path=str(kb_path),
        settings=Settings(anonymized_telemetry=False, allow_reset=False),
    )

    _CHROMA_CLIENT_CACHE[cache_key] = client
    return client


def _invalidate_chroma_cache() -> None:
    _CHROMA_CLIENT_CACHE.clear()
    _CHROMA_COLLECTION_CACHE.clear()


def query_chromadb(
    project_name,
    collection_name=None,
    data=None,
    root_folder: str | None = None,
    chroma_db_path: str | None = None,
):
    project_name = project_name or DEFAULT_PROJECT_NAME
    collection_name = collection_name or DEFAULT_COLLECTION_NAME
    local_chroma_path = _resolve_local_chroma_root(root_folder, chroma_db_path)

    try:
        payload = data or {}
        if not isinstance(payload, dict):
            return {
                "error": "Invalid query payload",
                "details": "Expected a dict with query_embedding and query options.",
            }

        query_embedding = payload.get("query_embedding")
        if query_embedding is None:
            return {
                "error": "Invalid query payload",
                "details": "Missing required field: query_embedding",
            }

        if hasattr(query_embedding, "tolist"):
            query_embedding = query_embedding.tolist()

        if not hasattr(query_embedding, "__len__") or len(query_embedding) == 0:
            return {
                "error": "Invalid query payload",
                "details": "query_embedding must be a non-empty list-like vector",
            }

        client = _local_chroma_client(
            project_name,
            root_folder=root_folder,
            chroma_db_path=chroma_db_path,
        )
        cache_key = (str(local_chroma_path), collection_name)
        collection = _CHROMA_COLLECTION_CACHE.get(cache_key)
        if collection is None:
            collection = client.get_collection(name=collection_name)
            _CHROMA_COLLECTION_CACHE[cache_key] = collection

        query_kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": int(payload.get("n_results", 10)),
            "include": payload.get("include", ["documents", "metadatas", "distances", "embeddings"]),
        }
        if payload.get("where") is not None:
            query_kwargs["where"] = payload.get("where")

        results = collection.query(**query_kwargs)
        return results

    except Exception as e:
        return {
            "error": "Failed to query local ChromaDB",
            "details": str(e),
            "project_name": project_name,
            "collection_name": collection_name,
            "local_path": str(local_chroma_path),
        }


def check_remote_chromadb_connection(project_name=None, collection_name=None):
    """Check connectivity to the local ChromaDB knowledge base for the current project."""
    project_name = project_name or DEFAULT_PROJECT_NAME
    collection_name = collection_name or DEFAULT_COLLECTION_NAME

    try:
        local_path = ROOT_BLOB_CACHE_ROOT
        if not local_path.exists():
            return {
                "status": "error",
                "project_name": project_name,
                "collection_name": collection_name,
                "local_path": str(local_path),
                "details": f"ChromaDB cache not available locally: {local_path}",
            }

        client = _local_chroma_client(project_name)
        collection = client.get_collection(name=collection_name)
        return {
            "status": "ok",
            "project_name": project_name,
            "collection_name": collection_name,
            "local_path": str(local_path),
            "central_health": {"status": "local", "collection_count": collection.count()},
        }
    except Exception as exc:
        return {
            "status": "error",
            "project_name": project_name,
            "collection_name": collection_name,
            "local_path": str(ROOT_BLOB_CACHE_ROOT),
            "details": str(exc),
        }
    

def is_substantial_question(question):
    """
    Vérifie si la question est suffisamment substantielle pour mériter des liens.
    Retourne False pour les questions trop courtes ou génériques.
    """
    if not question or len(question.strip()) < 10:
        return False
    
    # Compter les mots significatifs (au moins 3 caractères)
    words = [w for w in question.split() if len(w) >= 3]
    if len(words) < 3:
        return False
    
    # Liste de phrases génériques qui ne méritent pas de liens
    generic_phrases = [
        'pose une question',
        'aide moi',
        'bonjour',
        'salut',
        'merci',
        'hello',
        'hi',
        'help',
        'ask a question',
        'ask question',
    ]
    
    question_lower = question.lower().strip()
    for phrase in generic_phrases:
        if question_lower == phrase or question_lower == phrase + '?':
            return False
    
    return True

def extract_pmids_from_text(text):
    """Extrait toutes les références PMID d'un texte."""
    return re.findall(r'PMID:\s*\d+', text)

def get_links_from_contexts(contexts, metadatas=None, agent=None):
    """Extract links from contexts and metadata.
    
    Priority:
    1. Check metadatas for 'links' field (new ChromaDB format)
    2. Extract from matched chunks text (fallback)
    3. Look up chunk_0 of source documents (last resort)
    """
    links = set()
    
    # Priority 1: Check metadatas for direct link references (new format)
    if metadatas:
        for meta in metadatas:
            if isinstance(meta, dict) and 'links' in meta and meta['links']:
                # Links are stored as comma-separated string
                link_list = meta['links'].split(',')
                for link in link_list:
                    link = link.strip()
                    if link:
                        links.add(f"PMID: {link}")
                        print(f"[Metadata] Found link in metadata: PMID: {link}")
    
    # If we found links in metadata, return them immediately
    if links:
        return list(links)
    
    # Priority 2: Fallback - check the matched chunks text themselves
    for doc in contexts:
        links.update(extract_pmids_from_text(doc))
     
    return list(links)


def ask_question_stream(
    question,
    language="fr",
    timezone="UTC",
    locale="fr-FR",
    llm_model=None,
    llm_provider=None,
    kb_root_folder=None,
    chroma_db_path=None,
    top_k=5,
    conversation_history=None,
    session=None,
    question_id=None,
    agent=None,
):
    """Streaming version of ask_question with language support and conversation history"""

    # Use conversation_history if provided, otherwise empty list
    if conversation_history is None:
        conversation_history = []

    # Build history_text for refusal_engine
    history_text = ""
    if conversation_history and len(conversation_history) > 1:
        history_text = "\n\nHISTORIQUE DE LA CONVERSATION:\n"
        recent_history = conversation_history[-7:-1] if len(conversation_history) > 1 else []
        for msg in recent_history:
            role_label = "Utilisateur" if msg['role'] == 'user' else "Assistant"
            history_text += f"{role_label}: {msg['content']}\n"

    # context is not available yet (need ChromaDB), so pass empty string for now
    # refusal_result = validate_user_query(question, llm_call_fn=None, language=language)
    # if refusal_result and refusal_result.get("decision") == "refuse":
    #     # Store empty links list in session for refusal
    #     if session is not None and question_id is not None:
    #         if 'links' not in session:
    #             session['links'] = {}
    #         session['links'][question_id] = []
    #     yield "__REFUSAL__"
    #     yield refusal_result["answer"]
    #     return


    try:
        client = get_gateway_client(provider_override=llm_provider)

        # Get embedding for the question
        query_emb = create_embedding(
            input_text=question,
            model_name="text-embedding-3-large",
            provider_override=llm_provider,
        )

        # Query ChromaDB
        query_params = {
            "query_embedding": query_emb,
            "n_results": top_k,
            "include": ['documents', 'metadatas']
        }
            
        # Ensure query_params is JSON serializable
        query_params = json.loads(json.dumps(query_params, default=str))
        results = query_chromadb(
            project_name="nutrifaq",
            collection_name="nutrifaq-collection",
            data=query_params,
            root_folder=kb_root_folder,
            chroma_db_path=chroma_db_path,
        )

        if not isinstance(results, dict):
            yield "Knowledge base query returned an unexpected response format."
            return

        if results.get("error"):
            details = results.get("details", "")
            yield f"Knowledge base query failed: {details or results['error']}"
            return

        documents = results.get("documents")
        if not documents or not isinstance(documents, list):
            yield "No relevant information found. Please make sure you have indexed some transcripts."
            return

        top_documents = documents[0] if len(documents) > 0 and isinstance(documents[0], list) else []
        if not top_documents:
            yield "No relevant information found. Please make sure you have indexed some transcripts."
            return

        # Build context from results
        contexts = []
        for i, doc in enumerate(top_documents):
            contexts.append(doc)
        context = "\n\n".join(contexts)

        # Extraire les liens du contexte (with source metadata lookup)
        # Only extract links for substantial questions (not for generic/short questions)
        links = []
        if is_substantial_question(question):
            raw_metadatas = results.get("metadatas")
            metadatas = raw_metadatas[0] if isinstance(raw_metadatas, list) and len(raw_metadatas) > 0 else []
            links = get_links_from_contexts(contexts, metadatas=metadatas, agent=agent)
        
        # Save links in session if provided
        if session is not None and question_id is not None:
            if 'links' not in session:
                session['links'] = {}
            session['links'][question_id] = links

        # Build prompt using template from JSON
        prompt = build_prompt_from_template(language, context, question, history_text, agent=agent)

        if not prompt:
            yield "Error: Unable to load prompt template."
            return

        # Get streaming response from Vercel AI Gateway
        requested_model = (llm_model or "").strip()
        model_name = requested_model 
        
        stream = create_chat_completion_stream(
            client=client,
            model_name=model_name,
            provider_override=llm_provider,
            prompt=prompt,
            temperature=1.0,
        )
        first_chunk = True
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue

            first_choice = chunk.choices[0]
            delta = getattr(first_choice, "delta", None)
            content = getattr(delta, "content", None) if delta is not None else None

            if content is not None:
                # Strip leading whitespace from first chunk only
                if first_chunk:
                    content = content.lstrip()
                    first_chunk = False
                if content:
                    yield content

  

    except Exception as e:
        yield f"Error processing your question: {str(e)}"

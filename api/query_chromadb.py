import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings
from openai import OpenAI
from api.refusal_engine import validate_user_query

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / '.env')

# Initialize ChromaDB client (local storage)
_COLLECTION_CACHE = {}

DEFAULT_PROJECT_NAME = os.getenv("KNOWLEDGE_BASE_NAME", "nutria")
DEFAULT_COLLECTION_NAME = os.getenv("DEFAULT_COLLECTION_NAME", "gdrive_documents")
VECTOR_DB_DIRNAME = os.getenv("VECTOR_DB_DIRNAME", "chroma_db")

# Initialize Vercel AI Gateway client (OpenAI-compatible)
# See https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-chat-completions
client = OpenAI(
    api_key=os.getenv("AI_GATEWAY_API_KEY"),
    base_url="https://ai-gateway.vercel.sh/v1"
)


def load_style_guides():
    """Load style guides from JSON file"""
    try:
        with open(PROJECT_ROOT / 'config' / 'style_guides.json', 'r', encoding='utf-8') as f:
            style_data = json.load(f)
        
        # Format the style guides for use in prompts
        formatted_guides = {}
        for lang, data in style_data.items():
            guide = f"# {data['title']}\n\n"
            guide += f"\n## {data['characteristic_expressions']['title']}\n"
            for phrase in data['characteristic_expressions']['phrases']:
                guide += f"- \"{phrase}\"\n"
            guide += f"\n## {data['tone_and_voice']['title']}\n"
            for char in data['tone_and_voice']['characteristics']:
                guide += f"- {char}\n"
            guide += f"\n## {data['key_messages']['title']}\n"
            for msg in data['key_messages']['messages']:
                guide += f"- \"{msg}\"\n"
            formatted_guides[lang] = guide
        
        return formatted_guides, style_data
    except Exception as e:
        return {}, {}

def load_system_prompts():
    """Load system prompts from JSON file"""
    try:
        with open(PROJECT_ROOT / 'api/config' / 'system_prompts.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return {}

def load_prompts(kb_name=None):
    """
    Load prompts from JSON file in the knowledge base folder (single-agent setup)
    
    Args:
        kb_name: Ignored for single-agent setup
    """
    try:
        kb_path = PROJECT_ROOT / "api/config"
        prompts_path = kb_path / 'prompts.json'
        with open(prompts_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return {}

def build_prompt_from_template(language, context, question, history_text="", agent=None):
    """Build a complete prompt from the JSON template. Returns (prompt, model_config)"""
    prompts_data = load_prompts(kb_name=agent)
    lang_data = prompts_data.get(language, prompts_data.get("fr", {}))
    
    # Extract model configuration
    model_config = {
        "supplier": prompts_data.get("model_supplier", "openai"),
        "name": prompts_data.get("model_name", "gpt-4o-mini")
    }
    
    if not lang_data:
        return None, model_config
    
    # Build communication style content
    comm_style = lang_data.get('communication_style', {})
    tone = comm_style.get('tone_and_voice', {})
    recurring = comm_style.get('recurring_messages', {})
    
    tone_content = f"## {tone.get('title', '')}\n"
    for char in tone.get('characteristics', []):
        tone_content += f"- {char}\n"
    
    recurring_content = f"\n## {recurring.get('title', '')}\n"
    for msg in recurring.get('messages', []):
        recurring_content += f"- « {msg} »\n"
    
    communication_style_content = tone_content + recurring_content
    
    # Build absolute rules content
    rules = lang_data.get('absolute_rules', {})
    rules_content = ""
    for rule in rules.get('rules', []):
        rules_content += f"- {rule}\n"
    
    # Build behavioral constraints content
    constraints = lang_data.get('behavioral_constraints', {})
    constraints_content = ""
    for constraint in constraints.get('constraints', []):
        constraints_content += f"- {constraint}\n"
    
    # Build the final prompt using the template
    template = lang_data.get('template', '')
    prompt = template.format(
        system_role=lang_data.get('system_role', ''),
        important_notice=lang_data.get('important_notice', ''),
        communication_style_title=comm_style.get('title', ''),
        communication_style_content=communication_style_content,
        absolute_rules_title=rules.get('title', ''),
        absolute_rules_content=rules_content,
        behavioral_constraints_title=constraints.get('title', ''),
        behavioral_constraints_content=constraints_content,
        context=context,
        history=history_text,
        question=question
    )
    
    return prompt, model_config


def _resolve_kb_root() -> Path:
    """Resolve the local knowledge-base root for this project."""
    override = os.getenv("KNOWLEDGE_BASE_ROOT")
    if override:
        return Path(override)
    return PROJECT_ROOT / "knowledge-base"


def _get_local_collection(project_name: str, collection_name: str):
    """Return a local persisted ChromaDB collection."""
    cache_key = f"{project_name}:{collection_name}"
    if cache_key in _COLLECTION_CACHE:
        return _COLLECTION_CACHE[cache_key]

    kb_root = _resolve_kb_root()
    db_path = kb_root / project_name / VECTOR_DB_DIRNAME
    if not db_path.exists():
        raise FileNotFoundError(f"Local ChromaDB folder not found: {db_path}")

    local_client = chromadb.PersistentClient(
        path=str(db_path),
        settings=Settings(anonymized_telemetry=False, allow_reset=False),
    )
    local_collection = local_client.get_collection(name=collection_name)
    _COLLECTION_CACHE[cache_key] = local_collection
    return local_collection

def query_chromadb(project_name, collection_name=None, data=None):
    try:
        project_name = project_name or DEFAULT_PROJECT_NAME
        collection_name = collection_name or DEFAULT_COLLECTION_NAME
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

        local_collection = _get_local_collection(project_name, collection_name)

        query_args = {
            "query_embeddings": [query_embedding],
            "n_results": int(payload.get("n_results", 10)),
            "include": payload.get("include", ["documents", "metadatas"]),
        }
        if payload.get("where") is not None:
            query_args["where"] = payload.get("where")

        return local_collection.query(**query_args)

    except Exception as e:
        return {
            "error": "Failed to query local ChromaDB",
            "details": str(e),
            "project_name": project_name,
            "collection_name": collection_name,
            "knowledge_base_root": str(_resolve_kb_root()),
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


def ask_question_stream(question, language="fr", timezone="UTC", locale="fr-FR", top_k=5, conversation_history=None, session=None, question_id=None, agent=None):
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
    refusal_result = validate_user_query(question, llm_call_fn=None, language=language)
    if refusal_result and refusal_result.get("decision") == "refuse":
        # Store empty links list in session for refusal
        if session is not None and question_id is not None:
            if 'links' not in session:
                session['links'] = {}
            session['links'][question_id] = []
        yield "__REFUSAL__"
        yield refusal_result["answer"]
        return


    try:
        # Get embedding for the question
        query_emb = client.embeddings.create(
            model="text-embedding-3-large", 
            input=question
        ).data[0].embedding

        # Query ChromaDB
        query_params = {
            "query_embedding": query_emb,
            "n_results": top_k,
            "include": ['documents', 'metadatas']
        }
            
        # Ensure query_params is JSON serializable
        query_params = json.loads(json.dumps(query_params, default=str))
        results = query_chromadb(project_name="nutria", collection_name="gdrive_documents", data=query_params)

        if not isinstance(results, dict):
            yield "Knowledge base query returned an unexpected response format."
            return

        if results.get("error"):
            details = results.get("details", "")
            yield f"Knowledge base query failed: {details or results['error']}"
            return

        documents = results.get("documents")
        if not documents or not isinstance(documents, list) or not documents[0]:
            yield "No relevant information found. Please make sure you have indexed some transcripts."
            return

        # Build context from results
        contexts = []
        for i, doc in enumerate(documents[0]):
            contexts.append(doc)
        context = "\n\n".join(contexts)

        # Extraire les liens du contexte (with source metadata lookup)
        # Only extract links for substantial questions (not for generic/short questions)
        links = []
        if is_substantial_question(question):
            metadatas = results.get('metadatas', [[]])[0]
            links = get_links_from_contexts(contexts, metadatas=metadatas, agent=agent)
        
        # Save links in session if provided
        if session is not None and question_id is not None:
            if 'links' not in session:
                session['links'] = {}
            session['links'][question_id] = links

        # Build prompt using template from JSON
        prompt, model_config = build_prompt_from_template(language, context, question, history_text, agent=agent)
        
        if not prompt:
            yield "Error: Unable to load prompt template."
            return

        # Get streaming response from Vercel AI Gateway
        model_name = model_config.get('name', 'openai/gpt-4o-mini')
        
        stream = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=1.0,
            stream=True
        )
        first_chunk = True
        answer = ""
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                # Strip leading whitespace from first chunk only
                if first_chunk:
                    content = content.lstrip()
                    first_chunk = False
                if content:
                    answer += content
                    yield content

    except Exception as e:
        yield f"Error processing your question: {str(e)}"

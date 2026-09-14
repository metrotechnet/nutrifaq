from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from openai import OpenAI
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
import json
import os
import io
from tqdm import tqdm
from pathlib import Path
from dotenv import load_dotenv
import PyPDF2
import docx
from datetime import datetime

# Load environment variables
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / '.env')

# Extract config values from environment variables
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID", "")
GDRIVE_CREDENTIALS_PATH = os.getenv("GDRIVE_CREDENTIALS_PATH", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# Initialize Vercel AI Gateway client (OpenAI-compatible)
# See https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-chat-completions
client = OpenAI(
    api_key=os.getenv("AI_GATEWAY_API_KEY"),
    base_url="https://ai-gateway.vercel.sh/v1"
)


def get_agent_paths(agent=None):
    """Get knowledge base paths for specific agent"""
    kb_name = agent 
    kb_path = PROJECT_ROOT / "knowledge-base" / kb_name
    
    return {
        'kb_path': kb_path,
        'documents_dir': str(kb_path / "documents"),
        'extracted_dir': str(kb_path / "extracted_texts"),
        'chroma_db_dir': str(kb_path / "chroma_db")
    }

def get_chroma_collection(agent=None):
    """Get or create ChromaDB collection for specific agent"""
    paths = get_agent_paths(agent)
    
    # Setup folders
    os.makedirs(paths['documents_dir'], exist_ok=True)
    os.makedirs(paths['extracted_dir'], exist_ok=True)
    os.makedirs(paths['chroma_db_dir'], exist_ok=True)
    
    ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=OPENAI_API_KEY, model_name="text-embedding-3-large"
    )
    chroma_client = chromadb.PersistentClient(
        path=paths['chroma_db_dir'],
        settings=Settings(
            anonymized_telemetry=False,
            allow_reset=False
        )
    )
    collection = chroma_client.get_or_create_collection(
        name="gdrive_documents", embedding_function=ef
    )
    return collection, paths

# Google Drive authentication
drive_service = None
gdrive_authenticated = False

def authenticate_gdrive():
    """Authenticate with Google Drive using service account"""
    global drive_service, gdrive_authenticated
    try:
        print(f"Attempting Google Drive authentication...")
        
        if not GDRIVE_CREDENTIALS_PATH or not os.path.exists(GDRIVE_CREDENTIALS_PATH):
            print(f"❌ Credentials file not found: {GDRIVE_CREDENTIALS_PATH}")
            return False
        
        credentials = service_account.Credentials.from_service_account_file(
            GDRIVE_CREDENTIALS_PATH,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        
        drive_service = build('drive', 'v3', credentials=credentials)
        
        # Test connection
        drive_service.files().list(pageSize=1).execute()
        
        gdrive_authenticated = True
        print("✅ Google Drive authentication successful")
        return True
    except Exception as e:
        print(f"❌ Google Drive authentication failed: {str(e)}")
        print("⚠️  Google Drive functionality will be disabled")
        gdrive_authenticated = False
        return False


def list_files_in_folder(folder_id=None, limit=None):
    """List files in a Google Drive folder"""
    if not gdrive_authenticated:
        print("❌ Google Drive not authenticated")
        return []
    
    folder_id = folder_id or GDRIVE_FOLDER_ID
    
    try:
        query = f"'{folder_id}' in parents and trashed=false"
        
        # Supported document types
        mime_types = [
            'application/pdf',
            'application/vnd.google-apps.document',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'text/plain'
        ]
        
        mime_query = " or ".join([f"mimeType='{mt}'" for mt in mime_types])
        query += f" and ({mime_query})"
        
        results = drive_service.files().list(
            q=query,
            pageSize=limit or 100,
            fields="files(id, name, mimeType, modifiedTime, size)"
        ).execute()
        
        files = results.get('files', [])
        print(f"📁 Found {len(files)} documents in folder")
        return files
    except Exception as e:
        print(f"❌ Error listing files: {str(e)}")
        return []

def download_file(file_id, file_name, mime_type, documents_dir):
    """Download a file from Google Drive"""
    try:
        file_path = os.path.join(documents_dir, file_name)
        
        # Google Docs need to be exported
        if mime_type == 'application/vnd.google-apps.document':
            request = drive_service.files().export_media(
                fileId=file_id,
                mimeType='application/pdf'
            )
            file_path = file_path.replace('.gdoc', '.pdf')
        else:
            request = drive_service.files().get_media(fileId=file_id)
        
        fh = io.FileIO(file_path, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        fh.close()
        return file_path
    except Exception as e:
        print(f"❌ Error downloading {file_name}: {str(e)}")
        return None

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF file"""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        print(f"❌ Error extracting text from PDF: {str(e)}")
        return ""

def extract_text_from_docx(docx_path):
    """Extract text from DOCX file"""
    try:
        doc = docx.Document(docx_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    except Exception as e:
        print(f"❌ Error extracting text from DOCX: {str(e)}")
        return ""

def extract_text_from_txt(txt_path):
    """Extract text from TXT file"""
    try:
        with open(txt_path, 'r', encoding='utf-8') as file:
            return file.read().strip()
    except Exception as e:
        print(f"❌ Error reading TXT file: {str(e)}")
        return ""

def extract_text_from_file(file_path, mime_type):
    """Extract text based on file type"""
    if mime_type == 'application/pdf' or file_path.endswith('.pdf'):
        return extract_text_from_pdf(file_path)
    elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        return extract_text_from_docx(file_path)
    elif mime_type == 'text/plain':
        return extract_text_from_txt(file_path)
    else:
        print(f"⚠️  Unsupported file type: {mime_type}")
        return ""

def process_document(file_info, collection, paths):
    """Process a single document: download, extract text, and index"""
    file_id = file_info['id']
    file_name = file_info['name']
    mime_type = file_info['mimeType']
    
    print(f"📄 Processing: {file_name}")
    
    # Check if already indexed
    try:
        existing = collection.get(where={"file_id": file_id})
        if existing['ids']:
            print(f"⏭️  Already indexed: {file_name}")
            return True
    except:
        pass
    
    # Download file
    file_path = download_file(file_id, file_name, mime_type, paths['documents_dir'])
    if not file_path:
        return False
    
    # Extract text
    text = extract_text_from_file(file_path, mime_type)
    if not text:
        print(f"⚠️  No text extracted from {file_name}")
        return False
    
    # Save extracted text
    text_path = os.path.join(paths['extracted_dir'], f"{file_id}.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text)
    
    print(f"✅ Extracted {len(text)} characters from {file_name}")
    
    # Chunk text and add to ChromaDB
    chunk_size = 1000
    overlap = 100
    chunks = []
    
    for i in range(0, len(text), chunk_size - overlap):
        chunk = text[i:i + chunk_size]
        if chunk.strip():
            chunks.append(chunk)
    
    # Add chunks to ChromaDB
    for i, chunk in enumerate(chunks):
        collection.add(
            documents=[chunk],
            metadatas=[{
                "source": file_name,
                "file_id": file_id,
                "chunk": i,
                "mime_type": mime_type,
                "indexed_at": datetime.now().isoformat()
            }],
            ids=[f"{file_id}_chunk_{i}"]
        )
    
    print(f"✅ Indexed {len(chunks)} chunks from {file_name}")
    return True

def run_pipeline(limit=None, folder_id=None, agent=None):
    """Main pipeline: list, download, extract, and index documents from Google Drive
    
    Args:
        limit: Maximum number of files to process
        folder_id: Google Drive folder ID (default from env)
        agent: Agent/knowledge base identifier (default from env)
    """
    if not gdrive_authenticated:
        print("❌ Cannot run pipeline: Google Drive authentication required but failed")
        print("📋 Available options:")
        print("  1. Check GDRIVE_CREDENTIALS_PATH in .env file")
        print("  2. Ensure GDRIVE_FOLDER_ID is set in .env file")
        print("  3. Try calling retry_gdrive_auth() to retry authentication")
        return {"error": "Google Drive authentication required", "authenticated": False}
    
    folder_id = folder_id or GDRIVE_FOLDER_ID
    
    if not folder_id:
        print("❌ GDRIVE_FOLDER_ID not configured")
        return {"error": "Folder ID not configured", "authenticated": True}
    
    # Get collection and paths for this agent
    kb_name = agent 
    print(f"📦 Processing for knowledge base: {kb_name}")
    collection, paths = get_chroma_collection(agent)
    
    # List files
    files = list_files_in_folder(folder_id, limit)
    
    if not files:
        print("⚠️  No documents found in folder")
        return {"processed": 0, "total": 0, "authenticated": True}
    
    # Process each file
    success_count = 0
    for file_info in tqdm(files, desc=f"Processing documents for {kb_name}"):
        if process_document(file_info, collection, paths):
            success_count += 1
    
    print(f"✅ Pipeline completed for {kb_name}: {success_count}/{len(files)} documents processed")
    
    return {
        "processed": success_count,
        "total": len(files),
        "authenticated": True
    }

def retry_gdrive_auth():
    """Retry Google Drive authentication"""
    return authenticate_gdrive()

def get_gdrive_status():
    """Get current Google Drive authentication status"""
    return {
        "authenticated": gdrive_authenticated,
        "folder_id": GDRIVE_FOLDER_ID if gdrive_authenticated else "Not configured",
        "credentials_path": GDRIVE_CREDENTIALS_PATH if gdrive_authenticated else "Not configured"
    }

def get_indexed_documents(agent=None):
    """Get list of indexed documents from ChromaDB
    
    Args:
        agent: Agent/knowledge base identifier (default from env)
    """
    try:
        collection, paths = get_chroma_collection(agent)
        results = collection.get()
        
        # Group by file_id
        documents = {}
        for i, metadata in enumerate(results['metadatas']):
            file_id = metadata.get('file_id', 'unknown')
            if file_id not in documents:
                documents[file_id] = {
                    'source': metadata.get('source', 'Unknown'),
                    'chunks': 0,
                    'indexed_at': metadata.get('indexed_at', 'Unknown')
                }
            documents[file_id]['chunks'] += 1
        
        return list(documents.values())
    except Exception as e:
        print(f"❌ Error getting indexed documents: {str(e)}")
        return []

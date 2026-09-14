# Nutria Agent – Documentation
# IMX Agent Factory 🧠

This is the main documentation for the **Nutria Agent** project, based on the IMX Agent Factory template. It describes the features, architecture, and usage for this specialized agent.

An AI assistant platform template. Features a **Document Assistant** powered by RAG (Retrieval-Augmented Generation) over your documents, and a **Translation Agent** with speech-to-text via OpenAI Whisper. Built with FastAPI, ChromaDB, and OpenAI GPT-4o-mini.

## ✨ Features

- **🤖 Agent Architecture**: Specialized AI agent for your domain
  - **Document Assistant**: RAG-based Q&A over indexed documents and transcripts
  - **Translator Agent**: Real-time text & audio translation across 27 languages
  - **Customizable**: Configure prompts, knowledge base, and behavior
- **🎬 Automated Content Pipeline**: Process files from Google Drive — download, transcribe (Whisper), extract, chunk, and index
- **🔍 Vector Search**: ChromaDB for semantic retrieval over chunked documents
- **🎙️ Speech-to-Text**: OpenAI Whisper integration for audio transcription and translation
- **🌍 Bilingual UI**: Full French/English interface with i18n via `config.json`
- **⚡ Streaming Responses**: Real-time answers using Server-Sent Events (SSE)
- **📱 Responsive Design**: Mobile-first UI with breakpoints at 768px and 380px
- **🔐 Secure**: Environment-based secrets, no API keys in code
- **🛡️ Refusal Engine**: Configurable pattern-based refusal for out-of-scope questions

## 📁 Project Structure

```
template-agent/
├── app.py                    # FastAPI main server (82 lines - router registration)
├── api/                      # API layer (presentation layer)
│   ├── agents.py             # Agent configuration management & access control
│   ├── config.py             # Configuration loading and merging (common + agent-specific)
│   ├── logging.py            # Question/response logging with feedback tracking
│   ├── models.py             # Pydantic request models (QueryRequest, TranslateRequest)
│   ├── sessions.py           # Conversation session lifecycle management
│   ├── utils.py              # Utility functions
│   ├── README.md             # API architecture documentation
│   ├── __init__.py           # API module init
│   └── routes/               # API endpoint modules
│       ├── report.py          # Report endpoints (logs, comments, likes)
│       ├── agents.py         # Agent configuration API (keys, configs)
│       ├── pipeline.py       # Google Drive document indexing endpoint
│       ├── query.py          # RAG query endpoint (streaming SSE)
│       ├── sessions.py       # Session management API (reset, info)
│       ├── translation.py    # Translation & transcription endpoints
│       ├── tts.py            # Text-to-speech endpoint
│       └── __init__.py       # Routes module init
├── core/                     # Business logic (domain layer)
│   ├── query_chromadb.py     # ChromaDB vector search + LLM streaming (OpenAI + Gemini)
│   ├── translate.py          # Translation module (text + audio via Whisper/GPT/Gemini)
│   ├── update_gdrive.py      # Pipeline: Google Drive → transcribe → index
│   ├── create_agent.py       # Agent creation script (automated setup from config)
│   ├── refusal_engine.py     # Pattern-based refusal for off-topic questions
│   └── __init__.py           # Core module init
├── scripts/
│   ├── index_chromadb.py     # Index transcripts/documents to ChromaDB
│   ├── create_knowledge_base.ps1  # Create new knowledge base structure
│   ├── extract_docx.py       # DOCX text extraction utility
│   └── __init__.py           # Scripts module init
├── knowledge-base/          # All knowledge bases and agent configs
│   ├── common/              # Shared configuration for all agents
│   │   ├── config.json       # Shared UI translations (FR/EN), disclaimers, footer
│   │   ├── refusal_patterns.json  # Patterns to detect off-topic questions
│   │   ├── refusal_responses.json # Canned refusal responses
│   │   └── README_REFUSAL.md      # Refusal engine documentation
│   ├── nutria/              # Nutrition knowledge base
│   │   ├── config.json      # Nutrition agent-specific UI config
│   │   ├── prompts.json     # Agent system prompts + model config (OpenAI/Gemini)
│   │   ├── transcripts/     # Transcript .txt files
│   │   ├── documents/       # Source documents
│   │   ├── extracted_texts/ # Extracted text files for indexing
│   │   └── chroma_db/       # Vector database (auto-generated)
│   ├── translator/          # Translator agent
│   │   ├── config.json      # Translator agent-specific UI config
│   │   └── prompts.json     # Translator system prompts + model config
│   └── README.md            # Knowledge base documentation
├── videos/                   # Downloaded videos (shared)
├── templates/
│   └── index.html            # Main UI template (agent cards, selectors)
├── static/
│   ├── script.js             # Frontend JS (agent switching, translation, SSE)
│   ├── style.css             # Styles (pill selectors, responsive, dark theme)
│   ├── config.js             # Agent definitions (single-agent: nutria)
│   ├── logo-imx.png          # IMX logo
│   └── favicon.ico           # Favicon
├── tests/
│   ├── test_questions.json   # Test questions for validation
│   └── __init__.py           # Tests module init
├── requirements.txt          # Python dependencies
├── Dockerfile                # Container config for Cloud Run
├── firebase.json             # Firebase Hosting configuration
├── .firebaserc               # Firebase project reference
├── build.bat                 # Cloud Build script (Docker image)
├── deploy-backend.bat        # Cloud Run deployment (calls build.bat)
├── deploy-frontend.bat       # Firebase Hosting deployment
├── setup_scheduler.ps1       # Cloud Scheduler configuration
├── start_server.ps1          # Start both backend + frontend (PowerShell)
├── start_backend.ps1         # Start backend only (PowerShell)
├── start_frontend.ps1        # Start frontend only (PowerShell)
├── serve_frontend.py         # Custom frontend server (serves index.html at root)
├── startup.sh                # Container startup script
├── .env                      # Environment variables (not in git)
├── agent-config.example.json # Example configuration for creating agents
└── README.md                 # This file
```

## ⚙️ Setup

### 1. Clone and Navigate

```bash
cd c:\dev\template-agent
```

### 2. Create Virtual Environment

```powershell
cd c:\dev\template-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Configure Environment

Create a `.env` file by copying from `.env.example`:

```bash
cp .env.example .env
```

Then edit `.env` with your actual values. See [.env.example](.env.example) for all available configuration parameters with descriptions, including:

- **API Keys**: OpenAI, Gemini
- **Knowledge Base**: Which knowledge base folder to use (defaults to `agent`)
- **GCP Settings**: Project ID, Region, Service Name, Memory, Timeout
- **Google Drive**: Folder ID for knowledge base sync
- **Frontend**: Backend URL for Firebase deployment
- **Optional**: Instagram credentials for social media integration

### 4. Set Up Knowledge Base

The project uses a modular knowledge base system located in `knowledge-base/`. By default, the `agent` knowledge base is used. The `nutria` nutrition knowledge base is included as an example.

**To create a new knowledge base**:

```powershell
# Using the helper script
.\scripts\create_knowledge_base.ps1 -Name "my-kb"

# Or manually create the structure
mkdir knowledge-base\my-kb
mkdir knowledge-base\my-kb\transcripts
mkdir knowledge-base\my-kb\documents
mkdir knowledge-base\my-kb\extracted_texts
```

See [knowledge-base/README.md](knowledge-base/README.md) for complete documentation.

### 5. Add Documents

### 5. Add Documents

Place your files in the appropriate knowledge base folder:
- Transcript files (`.txt`) in `knowledge-base/agent/transcripts/`
- Document files (`.json`) in `knowledge-base/agent/documents/`
- Extracted text files (`.txt`) in `knowledge-base/agent/extracted_texts/`

**Note**: To use a different knowledge base (like `nutria`), set `KNOWLEDGE_BASE=nutria` in your `.env` file.

## 🛠️ Usage

### Index Documents to ChromaDB

```powershell
# Activate virtual environment first
.\.venv\Scripts\Activate.ps1

# Navigate to the project directory
cd c:\dev\template-agent

# Index the default knowledge base (agent)
python scripts/index_chromadb.py

# Index a specific knowledge base
python scripts/index_chromadb.py my-kb extracted_texts

# Index transcripts folder instead
python scripts/index_chromadb.py agent transcripts
```

This will process files from the specified knowledge base folder, creating a vector database in `knowledge-base/{kb-name}/chroma_db/`.

### Google Drive Pipeline

```powershell
# Download, transcribe, and index content from Google Drive
python -c "from core.update_gdrive import run_pipeline; run_pipeline()"
```

Or via API:

```bash
curl -X POST http://localhost:8080/update
```

See [GDRIVE_SETUP.md](GDRIVE_SETUP.md) for Google Drive service account configuration.

## 🤖 Creating Custom Agents

Create a new agent with automated setup:

### 1. Prepare Configuration

```bash
# Copy example configuration
cp agent-config.example.json my-agent-config.json

# Edit with your agent details
nano my-agent-config.json
```

### 2. Run Creation Script

```bash
# From agent-factory root (parent directory)
cd ..
python scripts/create_agent.py my-agent-config.json
```

This will:
- ✅ Create agent folder structure
- ✅ Copy and process documents (PDF, DOCX, TXT, JSON)
- ✅ Create transcripts from all documents automatically
- ✅ Transcribe audio files using Whisper
- ✅ Index everything to ChromaDB
- ✅ Register agent in agents.json

### 3. Add Logo (Optional)

```bash
cp my-logo.png static/logos/logo-my-agent.png
```

### 4. Restart & Test

Restart the backend server and your agent will appear in the interface.

**📖 See [AGENT_CREATION.md](../doc/AGENT_CREATION.md) for complete guide and configuration reference.**

## 🏗️ Manual Knowledge Base Setup

If you prefer manual setup or need to customize an existing agent:

### Create New Knowledge Base

1. Copy the template:
   ```bash
   cp -r knowledge-base/template-agent knowledge-base/my-custom-agent
   ```

2. Edit `config.json` and `prompts.json` for your use case

3. Register the agent in `agents.json`

#### Option 1: Start Both Servers (Recommended)

```powershell
# Use PowerShell script to start both backend and frontend
.\start_server.ps1
```

This will start:
- **Backend API** at `http://localhost:8080`
- **Frontend UI** at `http://localhost:3000`

Access the application at **http://localhost:3000**

#### Option 2: Start Servers Separately

For development, you may want to start servers independently:

```powershell
# Terminal 1: Start backend only
.\start_backend.ps1

# Terminal 2: Start frontend only
.\start_frontend.ps1
```

This is useful when you need to:
- Restart one server without affecting the other
- Debug backend or frontend independently
- Run only the backend for API testing

#### Option 3: Start Backend Only

```powershell
# Manually with venv activated
python app.py
```

Access the API at **http://localhost:8080** (no UI, API only)


## 🤖 Agents

### Assistant Nutrition (nutria)

RAG-based assistant that answers questions using indexed documents and transcripts. Uses ChromaDB for semantic search and configurable LLM (OpenAI GPT-4o-mini or Google Gemini 2.0) for response generation with source citations.

**Endpoints:**
- `POST /query` — Streaming chat with SSE (supports conversation history, session management)

### Traducteur (translator)

Real-time translation agent supporting 27 languages. Accepts both text and audio input. Uses configurable LLM (OpenAI or Gemini).

**Endpoints:**
- `GET /api/languages` — List supported languages
- `POST /api/translate` — Translate text (streaming SSE)
- `POST /api/translate_audio` — Transcribe & translate audio file (Whisper + LLM)
- `POST /api/transcribe_audio` — Transcribe audio to text (Whisper only)

**Supported Languages:** French, English, Spanish, German, Italian, Portuguese, Chinese, Japanese, Korean, Arabic, Russian, Hindi, Dutch, Polish, Swedish, Turkish, Vietnamese, Thai, Indonesian, Czech, Romanian, Hungarian, Greek, Hebrew, Danish, Finnish, Norwegian.

## 📚 Knowledge Base System

The application uses a modular knowledge base system that allows you to:
- Maintain multiple separate knowledge bases
- Switch between knowledge bases by changing `.env`
- Create domain-specific agents with different document sets

### Structure

Each knowledge base is a self-contained folder in `knowledge-base/`:

```
knowledge-base/
├── agent/                      # Default knowledge base
│   ├── transcripts/           # Audio transcriptions
│   ├── documents/             # Source documents
│   ├── extracted_texts/       # Processed texts
│   └── chroma_db/             # Vector database
├── nutria/                    # Example: Nutrition knowledge base
│   ├── transcripts/
│   ├── documents/
│   ├── extracted_texts/
│   └── chroma_db/
└── common/                    # Shared configuration
    ├── config.json            # Shared UI elements
    ├── refusal_patterns.json
    └── refusal_responses.json
```

### Creating a New Knowledge Base

**Using the helper script**:
```powershell
.\scripts\create_knowledge_base.ps1 -Name "medical-kb"
```

**Manual creation**:
```bash
mkdir knowledge-base/medical-kb
mkdir knowledge-base/medical-kb/{transcripts,documents,extracted_texts}
```

### Indexing a Knowledge Base

```bash
# Index specific knowledge base
python scripts/index_chromadb.py medical-kb extracted_texts
```

### Switching Knowledge Bases

Update `.env`:
```env
KNOWLEDGE_BASE=nutria
```

Then restart the application (or redeploy to Cloud Run). The agent will automatically use the specified knowledge base.

**Important for Deployment**: When deploying to Cloud Run, the `KNOWLEDGE_BASE` environment variable is automatically set from your `.env` file. Make sure to rebuild and redeploy after changing knowledge bases.

### Management

See [knowledge-base/README.md](knowledge-base/README.md) for complete documentation including:
- Creating and managing knowledge bases
- Reindexing and clearing databases
- Backup and restore procedures
- Troubleshooting tips

## ⚙️ Configuration System

The application uses a **layered configuration system** that separates shared UI elements from agent-specific customizations. This allows each agent to have its own branding, suggestions, and interface elements while maintaining consistent legal disclaimers and privacy policies.

### Configuration Files

1. **Shared Config** (`knowledge-base/common/config.json`)
   - Application branding (title, description)
   - Header and sidebar navigation
   - Cookie consent banner
   - Legal disclaimers and warnings
   - Privacy policy
   - About page
   - Language translations (27 languages)
   - Common message strings

2. **Agent-Specific Configs**
   - **Nutrition Agent**: `knowledge-base/nutria/config.json`
     - Custom app title: "Nutria | Agent Nutritionniste"
     - Nutrition-focused suggestions (🥗 nutrition, 💊 supplements, 🏋️ training, 💡 health)
     - Domain-specific disclaimers
     - Model configuration (model_supplier: openai/gemini, model_name: gpt-4o-mini/gemini-2.0-flash-exp)
   - **Translator Agent**: `knowledge-base/translator/config.json`
     - Custom app title: "Traducteur IA | Agent Multilingue"
     - Translation-specific UI (sourceLabel, targetLabel)
     - Translation suggestions (📝 text, 🎤 audio)
     - Model configuration for translation LLM

### How It Works

When the frontend requests configuration via `/api/get_config?agent=nutria`, the backend:
1. Loads the shared configuration
2. Loads the agent-specific configuration
3. Merges them (agent config overrides shared config)
4. Returns the merged configuration

```javascript
// Example: Frontend config loading
const config = await fetch('/api/get_config?agent=nutria').then(r => r.json());
// config now contains merged shared + agent-specific values
```

### Adding New Agents

To create a new agent with custom UI:

1. Create agent-specific config:
   ```bash
   cp knowledge-base/nutria/config.json knowledge-base/my-agent/config.json
   cp knowledge-base/nutria/prompts.json knowledge-base/my-agent/prompts.json
   ```

2. Customize the config:
   - Update `app.title` with agent branding
   - Modify `suggestions` with relevant actions
   - Customize `input.placeholder` and disclaimers
   - Set `model_supplier` (openai or gemini) and `model_name` in prompts.json

3. Register the agent in `agents.json` (if not already auto-discovered)
   - The backend automatically recognizes agents from the knowledge-base/ folder

## 🎯 Key Features

### Agent UI

- **Agent Selector**: Pill-styled dropdown in the header to switch between agents
- **Agent Cards**: Intro page with clickable cards for each agent
- **Chat Clearing**: Conversation resets when switching agents
- **Welcome Messages**: Each agent displays a localized welcome message on selection
- **Dynamic Placeholders**: Input placeholder and disclaimer update per agent

### Internationalization (i18n)

All UI text is stored in `config/config.json` under `fr` and `en` sections. The language toggle in the header switches between French and English. Agent names, welcome messages, suggestions, and disclaimers are all translatable.

### Vector Search (ChromaDB)

- Semantic search over chunked documents
- OpenAI text-embedding-3-large (3072 dimensions)
- Fast local queries, no cloud costs
- Source citation with document references

### Refusal Engine

Configurable pattern matching to detect and refuse off-topic questions gracefully. Patterns and responses are defined in `knowledge-base/common/refusal_patterns.json` and `knowledge-base/common/refusal_responses.json`.

See [knowledge-base/common/README_REFUSAL.md](knowledge-base/common/README_REFUSAL.md) for detailed documentation on the refusal engine.

## 🔧 Technical Stack

- **Backend**: FastAPI (modular architecture with clean separation: api/ layer + core/ layer), Python 3.11+
- **AI/ML**: OpenAI GPT-4o-mini / Gemini 2.0 (chat + translation), OpenAI Whisper (transcription)
- **Vector DB**: ChromaDB (local)
- **Embeddings**: OpenAI text-embedding-3-large (3072 dimensions)
- **Frontend**: HTML5, CSS3, JavaScript (ES6+)
- **i18n**: JSON-based config with `data-i18n` attributes
- **Cloud**: Google Cloud Run, Google Drive API
- **Configuration**: Environment variables (`.env`) + `knowledge-base/common/config.json` (shared) + agent-specific configs

## 🚀 Deployment

### Backend Deployment (Google Cloud Run)

```bash
# First build the Docker image
.\build-backend.bat

# Then deploy
.\deploy-backend.bat
```

This will:
1. Automatically build the Docker image using Cloud Build
2. Load configuration from `.env` (including `KNOWLEDGE_BASE`)
3. Deploy to Cloud Run with all environment variables
4. Configure CORS for Firebase hosting domain
5. Save backend URL to `.env` and `.backend-url.tmp`

**Important Files**:
- `.gcloudignore`: Controls which files are uploaded to Cloud Build (excludes .env, credentials, but **includes** knowledge-base JSON files)
- `.dockerignore`: Controls which files are copied into the Docker image

**Configuration** (via `.env`):
- Memory: 1Gi
- Timeout: 300s (5 minutes)
- Min instances: 1
- Max instances: 10
- CPU: 1

### Frontend Deployment (Firebase Hosting)

```bash
.\deploy-frontend.bat
```

This will:
1. Copy frontend files from `templates/` and `static/` to `public/`
2. Update file paths for Firebase hosting
3. Create config.js with backend URL
4. Deploy to Firebase Hosting

**CORS Configuration**: The backend is configured to allow requests from:
- `https://your-project.web.app`
- `https://your-project.firebaseapp.com`
- `http://localhost:3000` (local frontend development)
- `http://localhost:8080` (local backend-only development)

See [FIREBASE_DEPLOYMENT.md](FIREBASE_DEPLOYMENT.md) for detailed Firebase setup.

## 🔐 Security

- Environment-based secrets management
- No API keys in code or config files
- `.env` file excluded from version control
- Secure Cloud Run deployment with IAM
- Refusal engine for out-of-scope question handling

## 📝 Requirements

- **Python**: 3.11 or higher
- **Memory**: 2GB+ recommended
- **Storage**: 1GB for transcripts and database
- **APIs**: OpenAI API key required
- **GCP**: Google Cloud Project (optional, for Cloud Run deployment and Google Drive pipeline)

## 🐛 Troubleshooting

### ChromaDB Issues

```bash
# Re-index transcripts
python scripts/index_chromadb.py
```

### Server Won't Start

- Ensure `.env` file exists with `OPENAI_API_KEY`
- Verify Python 3.11+ is installed: `python --version`
- Check venv is activated: `.\.venv\Scripts\Activate.ps1`
- Install dependencies: `pip install -r requirements.txt`

### Translation Not Working

- Verify `OPENAI_API_KEY` is set (used for both Whisper and GPT-4o-mini)
- Check audio file format (supports mp3, wav, m4a, webm)

### Deployment Fails

- Check `.env` file exists and has all required variables
- Verify Cloud Build API is enabled
- Ensure billing is enabled on GCP project
- Check IAM permissions for Cloud Build service account

### CORS Errors

- Verify backend allows your frontend domain in CORS middleware
- Check backend URL in `static/js/backend-url.js`
- Ensure backend is deployed and accessible

## 💰 Cost Estimation

**Cloud Run** (~$20-50/month):
- CPU: $0.00002400/vCPU-second
- Memory: $0.00000250/GiB-second
- Free tier: 2M requests/month

**OpenAI API** (~$10-30/month):
- text-embedding-3-large: $0.13/1M tokens
- gpt-4o-mini: $0.15/1M input, $0.60/1M output
- Whisper: $0.006/minute of audio

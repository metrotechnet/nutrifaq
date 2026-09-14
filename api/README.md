# Nutria Agent – Documentation
# API Module Structure

This directory contains the modularized backend API for the **Nutria Agent** application. It describes the structure and purpose of each module for maintainability and clarity.

This directory contains the modularized backend API for the IMX Agent application.

## Directory Structure

```
api/
├── __init__.py                 # Module initialization
├── models.py                   # Pydantic data models (QueryRequest, TranslateRequest)
├── agents.py                   # Agent configuration and access control
├── config.py                   # Configuration loading and merging
├── sessions.py                 # Conversation session management
├── logging.py                  # Question/response logging with comments and likes
├── utils.py                    # Utility functions
└── routes/                     # API endpoint routes
    ├── __init__.py
    ├── query.py                # Main query endpoint (streaming RAG)
    ├── translation.py          # Translation and transcription endpoints
    ├── tts.py                  # Text-to-speech endpoint
    ├── report.py                # Report endpoints (logs, reports)
    ├── agents.py               # Agent configuration endpoints
    ├── sessions.py             # Session management endpoints
    └── pipeline.py             # Google Drive indexing pipeline
```

## Module Descriptions

### Core Modules

**models.py**
- Contains Pydantic models for API request validation
- `QueryRequest`: Question/query parameters
- `TranslateRequest`: Translation parameters

**agents.py**
- Agent configuration loading and caching
- Access key validation
- Agent metadata retrieval

**config.py**
- Configuration file loading (common.json, nutria/config.json, etc.)
- Deep merging of configuration dictionaries
- Agent-specific configuration handling

**sessions.py**
- Conversation session storage and management
- Session timeout handling
- Message history tracking

**logging.py**
- Question and response logging to JSON
- Comment and like/dislike functionality
- Medical disclaimer detection

**utils.py**
- Shared utility functions and constants

### Route Modules

**routes/query.py**
- `POST /query` - Main streaming RAG endpoint
- Handles conversation history, refusals, and link extraction

**routes/translation.py**
- `GET /api/languages` - List supported languages
- `POST /api/translate` - Text translation (streaming)
- `POST /api/transcribe_audio` - Audio transcription (Whisper)
- `POST /api/translate_audio` - Audio translation (Whisper + GPT)

**routes/tts.py**
- `POST /api/tts` - Text-to-speech conversion (OpenAI TTS)

**routes/report.py**
- `POST /api/add_comment` - Add comment to question
- `POST /api/like_answer` - Like/dislike answer
- `GET /api/download_log` - Download question log
- `GET /log_report` - View log report

**routes/agents.py**
- `GET /api/get_config` - Get agent configuration

**routes/sessions.py**
- `POST /api/reset_session` - Reset conversation session
- `GET /api/session_info` - Get session information

**routes/pipeline.py**
- `POST /update` - Trigger Google Drive document indexing

## Usage

The main `app.py` file imports and registers all route modules:

```python
from api.routes import query, translation, tts, report, config, sessions, update

app.include_router(query.router, tags=["query"])
app.include_router(translation.router, tags=["translation"])
# ... etc
```

## Benefits of This Structure

1. **Separation of Concerns** - Each module has a single, clear responsibility
2. **Maintainability** - Easier to locate and modify specific functionality
3. **Testability** - Individual modules can be tested in isolation
4. **Scalability** - New features can be added as new route modules
5. **Readability** - Smaller, focused files are easier to understand
6. **Reusability** - Core functions (agents, config, sessions) can be imported anywhere

## Migration Notes

The original 764-line `app.py` has been refactored into:
- 1 main app file (79 lines)
- 7 core module files
- 7 route module files

All functionality remains the same, just better organized.

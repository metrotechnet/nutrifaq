# API module overview

This folder contains the backend logic for NutriFAQ. The app is launched from `app.py` and the API routes are organized under `api/routes`.

## Current backend layout

```text
api/
├── graph_layer.py
├── models.py
├── orchestrator.py
├── utils.py
├── README.md
├── routes/
│   ├── __init__.py
│   ├── config.py
│   ├── datasets.py
│   ├── query.py
│   ├── report.py
│   ├── sessions.py
│   ├── translation.py
│   └── tts.py
├── services/
│   ├── config.py
│   ├── logging.py
│   ├── query_chromadb.py
│   ├── refusal_engine.py
│   ├── sessions.py
│   └── translate.py
└── config/
    ├── agent_config.json
    ├── common_config.json
    ├── prompts.json
    ├── refusal_patterns.json
    └── refusal_responses.json
```

## Route modules

### `services/query_chromadb.py`
Handles ChromaDB access, question retrieval, and streaming answer generation.

### `services/config.py`
Handles runtime configuration loading and deep merge.

### `services/logging.py`
Handles question/response logging and feedback persistence.

### `services/refusal_engine.py`
Handles pre-LLM refusal decisions and safety pattern matching.

### `services/sessions.py`
Handles in-memory conversation session tracking.

### `services/translate.py`
Handles text and audio translation/transcription.

### `routes/translation.py`
Handles language detection, translation endpoints, and translation helpers.

### `routes/tts.py`
Provides text-to-speech requests.

### `routes/report.py`
Handles logging/reporting endpoints and feedback-related actions.

### `routes/config.py`
Serves configuration data for frontend and runtime settings.

### `routes/sessions.py`
Tracks conversation/session state.

## Main app entry

The root app file registers the routing modules and exposes the FastAPI instance used by uvicorn:

```python
app.include_router(query.router, tags=["query"])
app.include_router(translation.router, tags=["translation"])
app.include_router(tts.router, tags=["tts"])
app.include_router(report.router, tags=["report"])
app.include_router(config_routes.router, tags=["config"])
app.include_router(sessions.router, tags=["sessions"])
```

## Run locally

```powershell
python app.py
```

Or via debug config in VS Code: `Python: API (FastAPI)`.

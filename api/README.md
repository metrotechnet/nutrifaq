# API module overview

This folder contains the backend logic for NutriFAQ. The app is launched from `app.py` and the API routes are organized under `api/routes`.

## Current backend layout

```text
api/
├── app_check.py
├── config.py
├── graph_layer.py
├── index_chromadb.py
├── logging.py
├── models.py
├── orchestrator.py
├── query_chromadb.py
├── refusal_engine.py
├── sessions.py
├── translate.py
├── update_gdrive.py
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
│   ├── tts.py
│   └── update.py
└── config/
    ├── agent_config.json
    ├── common_config.json
    ├── prompts.json
    ├── refusal_patterns.json
    └── refusal_responses.json
```

## Route modules

### `routes/query.py`
Handles user questions and the main retrieval workflow.

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

### `routes/update.py`
Processes data refresh and update tasks.

## Main app entry

The root app file registers the routing modules and exposes the FastAPI instance used by uvicorn:

```python
app.include_router(query.router, tags=["query"])
app.include_router(translation.router, tags=["translation"])
app.include_router(tts.router, tags=["tts"])
app.include_router(report.router, tags=["report"])
app.include_router(config_routes.router, tags=["config"])
app.include_router(sessions.router, tags=["sessions"])
app.include_router(update.router, tags=["update"])
```

## App Check note

Firebase App Check is intentionally disabled for this project. The backend App Check middleware file remains in the repo for reference, but it is not registered in `app.py`.

## Run locally

```powershell
python app.py
```

Or via debug config in VS Code: `Python: API (FastAPI)`.

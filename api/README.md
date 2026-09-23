# API module overview

This folder contains the backend logic for NutriFAQ.
The FastAPI app is started from `app.py`, which dynamically loads route modules under `api/routes`.

## Current backend layout

```text
api/
├── README.md
├── config/                  # JSON config used by backend logic
├── db_pipeline/             # indexing / regeneration helpers
├── routes/                  # API endpoints
├── schemas/                 # Pydantic schemas
└── services/                # business logic and integrations
```

## Routers currently loaded by app.py

- `api.routes.users`
- `api.routes.query`
- `api.routes.translation`
- `api.routes.tts`
- `api.routes.report`
- `api.routes.config`
- `api.routes.sessions`
- `api.routes.blob`
- `api.routes.database`
- `api.routes.publish`

## Endpoint groups (high level)

### Config and models

- `GET /api/get_config`
- `GET /api/models`

### Query and logs

- `GET /api/generated-questions`
- `POST /api/add_comment`
- `POST /api/like_answer`
- `GET /api/download_log`
- `POST /api/reset_question_log`

### Publish workflow

- `POST /api/publish`
- `POST /api/publish/revert`
- `GET /api/publish/status`
- `GET /api/publish/log`
- `POST /api/publish/log/reset`

### Blob and file management

- `GET /api/blob/files`
- `GET /api/blob/files/{blob_name:path}/download`
- `POST /api/blob/files/{blob_name:path}`
- `DELETE /api/blob/files/{blob_name:path}`
- `POST /api/blob/copy-container`
- `POST /api/blob/debug/reset-local`
- `POST /api/blob/debug/sync-local-to-blob`

### Database regeneration/indexing

- `GET /api/database/steps`
- `POST /api/database/run-step`
- `POST /api/database/extract-docx`
- `POST /api/database/extract-references`
- `POST /api/database/generate-transcripts-json`
- `POST /api/database/generate-questions`
- `POST /api/database/index-chromadb-json`
- `POST /api/database/regenerate`
- `POST /api/database/regenerate/cancel`
- `GET /api/database/regenerate/status`

### Translation and TTS

- `GET /api/languages`
- `POST /api/translate`
- `POST /api/transcribe_audio`
- `POST /api/translate_audio`
- `POST /api/tts`

### Sessions and users

- `POST /api/reset_session`
- `GET /api/session_info`
- `GET /api/users/me`
- `POST /api/users`
- `GET /api/users`
- `PUT /api/users/{user_object_id}/role`
- `DELETE /api/users/{user_object_id}/role`

## Service responsibilities

- `services/query_chromadb.py`: retrieval and answer generation over ChromaDB-backed data.
- `services/logging.py`: question/response logs, votes, and comments.
- `services/config.py`: runtime config load/merge.
- `services/refusal_engine.py`: refusal checks before LLM generation.
- `services/sessions.py`: conversation/session state.
- `services/startup_sync.py`: syncs blob databases on app startup.

## Run locally

```powershell
python app.py
```

or

```powershell
uvicorn app:app --reload --host 127.0.0.1 --port 8080
```

# API module overview

This folder contains the FastAPI backend for NutriFAQ (routes, schemas, services, and DB pipeline scripts).

## Folder layout

```text
api/
├── config/         # backend JSON config files (legacy/local helpers)
├── db_pipeline/    # extraction, transcript/question generation, Chroma indexing
├── routes/         # HTTP endpoints
├── schemas/        # Pydantic request/response models
├── services/       # core business logic and integrations
└── README.md
```

## Authentication and authorization

The backend uses Microsoft Entra ID bearer tokens for protected endpoints.

Current behavior:

- `/query` accepts either:
	- `Authorization: Bearer <entra_token>`
	- `X-Client-Key` matching `QUERY_ACCESS_KEY`
- Other protected endpoints require Entra bearer auth and ignore query-key access.
- `/query_debug` is admin-only.

Role model:

- Effective role is resolved from local role assignments when present.
- If no explicit assignment exists, authenticated Entra users default to `admin`.

## Main route groups

Query and chat:

- `POST /query`
- `POST /query_debug`
- `GET /api/generated-questions`

Publish and rollback:

- `POST /api/publish`
- `POST /api/publish/revert`
- `GET /api/publish/status`
- `GET /api/publish/log`
- `POST /api/publish/log/reset`

Blob/file operations:

- `GET /api/blob/files`
- `POST /api/blob/files/{blob_name:path}`
- `DELETE /api/blob/files/{blob_name:path}`
- `GET /api/blob/files/{blob_name:path}/download`
- `POST /api/blob/debug/reset-local`
- `POST /api/blob/debug/sync-local-to-blob`

Database regeneration:

- `GET /api/database/steps`
- `POST /api/database/run-step`
- `POST /api/database/regenerate`
- `POST /api/database/regenerate/cancel`
- `GET /api/database/regenerate/status`

User and roles:

- `GET /api/users/me`
- `GET /api/users`
- `POST /api/users`
- `PUT /api/users/{user_object_id}/role`
- `DELETE /api/users/{user_object_id}/role`

## Key services

- `services/query_chromadb.py`: retrieval + prompt building + streaming answer orchestration.
- `services/llm_service.py`: LLM client wrappers, retries, embeddings, and prompt template helpers.
- `services/database_regeneration_service.py`: end-to-end regeneration orchestration and progress status.
- `services/publish_service.py`: publish/revert jobs and operation status tracking.
- `services/blob_storage_service.py`: Azure Blob access, sync, upload, copy, and delete helpers.

## Run locally

```powershell
python app.py
```

or

```powershell
uvicorn app:app --reload --host 127.0.0.1 --port 8080
```

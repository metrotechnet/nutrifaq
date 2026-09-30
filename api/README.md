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

Third-party ingestion helpers:

- `POST /download_page`
- `GET /list_page`
- `DELETE /delete_page/{filename:path}`

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

## Third-party endpoints (X-Client-Key)

These routes are intended for external ingestion clients and are protected with:

- `X-Client-Key: <QUERY_ACCESS_KEY>`

If the key is missing or invalid, API returns `401`.
If `QUERY_ACCESS_KEY` is not configured server-side, API returns `500`.

### POST /download_page

Upload one file into `nutrifaq-dbase-main/documents`.

Request:

- `multipart/form-data`
- field: `file`

Validation:

- Missing filename -> `400 Missing filename.`
- Empty payload -> `400 Empty file.`

Success response example:

```json
{
	"status": "saved",
	"filename": "my-file.pdf",
	"path": "nutrifaq-dbase-main/documents/my-file.pdf"
}
```

### GET /list_page

List files currently present in `nutrifaq-dbase-main/documents`.

Success response example:

```json
{
	"status": "ok",
	"count": 2,
	"files": [
		{
			"filename": "doc-1.pdf",
			"size": 183245,
			"last_modified": 1790784000.123
		},
		{
			"filename": "doc-2.docx",
			"size": 48211,
			"last_modified": 1790784021.456
		}
	]
}
```

Notes:

- `last_modified` is a Unix timestamp (seconds).
- Returned files are direct children of the `documents` folder.

### DELETE /delete_page/{filename:path}

Delete one file by name from `nutrifaq-dbase-main/documents`.

Path parameter:

- `filename`: file name to delete.

Validation:

- Empty filename -> `400 Missing filename.`
- File not found -> `404 File not found.`

Success response example:

```json
{
	"status": "deleted",
	"filename": "doc-1.pdf"
}
```

### cURL examples

```bash
# List
curl -X GET "http://127.0.0.1:8080/list_page" \
	-H "X-Client-Key: YOUR_QUERY_ACCESS_KEY"

# Delete
curl -X DELETE "http://127.0.0.1:8080/delete_page/doc-1.pdf" \
	-H "X-Client-Key: YOUR_QUERY_ACCESS_KEY"
```

## Run locally

```powershell
python app.py
```

or

```powershell
uvicorn app:app --reload --host 127.0.0.1 --port 8080
```

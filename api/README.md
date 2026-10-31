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

The backend uses local JWT authentication powered by `fastapi-users`.

Current behavior:

- Login endpoint: `POST /auth/jwt/login`
- Registration endpoint: `POST /auth/register`
- Authenticated user endpoints: `/auth/users/*`
- Login smoke test script: `python scripts/test_login.py`
- `/query` accepts either:
	- `Authorization: Bearer <jwt-token>`
	- `X-Client-Key` matching `QUERY_ACCESS_KEY`
- Other protected endpoints require JWT bearer auth and ignore query-key access.
- `/query_debug` is admin-only.

Role model:

- Effective role is resolved from local role assignments when present.
- If no explicit assignment exists, superusers are `admin`, others are `client`.

Login test examples:

```powershell
python scripts/test_login.py
python scripts/test_login.py --email admin@imxtech.ca --password "your-password"
python scripts/test_login.py --base-url http://127.0.0.1:8080 --check-admin
```

### Azure SQL migration for auth users

To persist credentials across App Service deployments, move auth storage from local SQLite to Azure SQL.

Recommended environment settings:

- `AUTH_DB_BACKEND=azure_sql`
- `AUTH_SQL_SERVER=<server>.database.windows.net`
- `AUTH_SQL_DATABASE=<database-name>`
- `AUTH_SQL_USER=<sql-user>`
- `AUTH_SQL_PASSWORD=<sql-password>`
- `AUTH_SQL_PORT=1433` (optional)
- `AUTH_SQL_DRIVER=ODBC Driver 18 for SQL Server` (optional)

Alternative:

- Set `AUTH_DATABASE_URL` directly with an async SQLAlchemy URL (it takes precedence over `AUTH_DB_BACKEND`).

Notes:

- The backend auto-creates auth tables at startup (`initialize_auth`).
- Ensure the App Service runtime includes ODBC Driver 18 for SQL Server.

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

Database indexing:

- `GET /api/database/steps`
- `POST /api/database/run-step`
- `POST /api/database/indexing`
- `POST /api/database/indexing/cancel`
- `GET /api/database/indexing/status`

User and roles:

- `GET /api/users/me`
- `GET /api/users`
- `POST /api/users`
- `PUT /api/users/{user_object_id}/password`
- `PUT /api/users/{user_object_id}/role`
- `DELETE /api/users/{user_object_id}`
- `DELETE /api/users/{user_object_id}/role`

## Key services

- `services/query_chromadb.py`: retrieval + prompt building + streaming answer orchestration.
- `services/llm_service.py`: LLM client wrappers, retries, embeddings, and prompt template helpers.
- `services/indexation_service.py`: end-to-end indexation orchestration and progress status.
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

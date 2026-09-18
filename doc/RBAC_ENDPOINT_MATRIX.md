# RBAC Endpoint Matrix

Matrice des acces par endpoint pour l'API NutriFAQ.

## Roles

- `client`: acces a `POST /query` uniquement (hors endpoints publics)
- `collaborator`: acces aux endpoints operationnels
- `admin`: acces complet, y compris administration et operations sensibles

## Endpoints publics

| Endpoint | Methode | Role minimum |
|---|---|---|
| `/` | GET | public |
| `/health` | GET | public |

## Endpoints proteges

| Endpoint | Methode | Role minimum |
|---|---|---|
| `/query` | POST | client |
| `/api/get_config` | GET | collaborator |
| `/api/db/connection` | GET | collaborator |
| `/api/reset_session` | POST | collaborator |
| `/api/session_info` | GET | collaborator |
| `/api/languages` | GET | collaborator |
| `/api/translate` | POST | collaborator |
| `/api/transcribe_audio` | POST | collaborator |
| `/api/translate_audio` | POST | collaborator |
| `/api/tts` | POST | collaborator |
| `/api/add_comment` | POST | collaborator |
| `/api/like_answer` | POST | collaborator |
| `/api/download_log` | GET | admin |
| `/log_report` | GET | admin |
| `/api/users/me` | GET | collaborator |
| `/api/users` | GET | admin |
| `/api/users/{user_object_id}/role` | PUT | admin |
| `/api/users/{user_object_id}/role` | DELETE | admin |
| `/api/blob/files` | GET | admin |
| `/api/blob/files/{blob_name:path}/download` | GET | admin |
| `/api/blob/files/{blob_name:path}` | POST | admin |
| `/api/blob/files/{blob_name:path}` | DELETE | admin |
| `/api/database/steps` | GET | admin |
| `/api/database/run-step` | POST | admin |
| `/api/database/extract-docx` | POST | admin |
| `/api/database/extract-references` | POST | admin |
| `/api/database/generate-transcripts-json` | POST | admin |
| `/api/database/index-chromadb-json` | POST | admin |
| `/api/database/regenerate` | POST | admin |

## Note

- Les routes `datasets` existent dans `api/routes/datasets.py` mais ne sont pas montees dans `app.py` (`ROUTE_MODULES`), donc non exposees actuellement.

# NutriFAQ

NutriFAQ is a FastAPI-based nutrition assistant and nutrifaq-dbase Q&A app. It serves a browser frontend, indexes nutrition materials into ChromaDB, and answers user questions from the configured knowledge base.

Repository: https://github.com/metrotechnet/nutrifaq.git

## Features

- FastAPI backend with routed endpoints for queries, TTS, translation, sessions, reports, and config
- Retrieval-augmented search over the knowledge base in `nutrifaq-dbase/nutria`
- Browser frontend served from `templates/` and `static/`
- Firebase hosting/deployment configuration in the repo root
- Debug launch configuration for the API in `.vscode/launch.json`
- Rate limiting enabled by default for local API protection

## Current project structure

```text
NutriFAQ/
├── app.py
├── api/
│   ├── __init__.py
│   ├── graph_layer.py
│   ├── models.py
│   ├── orchestrator.py
│   ├── services/
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── query_chromadb.py
│   │   ├── refusal_engine.py
│   │   ├── sessions.py
│   │   └── translate.py
│   ├── utils.py
│   ├── README.md
│   └── routes/
│       ├── __init__.py
│       ├── config.py
│       ├── datasets.py
│       ├── query.py
│       ├── report.py
│       ├── sessions.py
│       ├── translation.py
│       ├── tts.py
│       └── blob.py
├── nutrifaq-dbase/
│   └── nutria/
│       ├── chroma_db/
│       ├── documents/
│       ├── extracted_texts/
│       ├── transcripts/
│       ├── build-database.bat
│       ├── references.json
│       └── transcripts_chromadb.json
├── static/
│   ├── js/
│   ├── logos/
│   └── style.css
├── templates/
│   ├── index.html
│   └── log_report.html
├── public/
│   └── ...
├── doc/
├── .vscode/
│   └── launch.json
├── requirements.txt
├── package.json
├── firebase.json
├── Dockerfile
├── serve_frontend.py
├── startup.sh
├── start-backend.ps1
├── start-frontend.ps1
├── build-backend.bat
├── deploy-backend.bat
├── deploy-frontend.bat
├── README.md
├── .gitignore
└── .vscode/
```

## Local setup

1. Open PowerShell in the repo root.
2. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Create a `.env` file if needed for your local configuration.

4. Start the API:

```powershell
python app.py
```

Or use the VS Code debug config in `.vscode/launch.json`.

## Debugging the API

Use the VS Code configuration named `Python: API (FastAPI)`.

It launches:

```text
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

## Notes

- Rate limiting is configured in `app.py` and defaults to `30 per day` and `10 per hour` by IP.
- The app is expected to run locally on port `8080`.

## Run locally

```powershell
python app.py
```

Or run the API from the VS Code debug panel with the configuration already added to the repo.

## GitHub repo

```text
https://github.com/metrotechnet/nutrifaq.git
```


### ChromaDB Issues

```bash
# Query helpers live under api/services/query_chromadb.py
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

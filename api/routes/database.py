"""Database regeneration routes.

Provides API endpoints to run the nutrifaq-dbase regeneration pipeline
using scripts under api/db_pipeline.
"""

import os
from contextlib import contextmanager

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from api.services.database_regeneration_service import (
    list_regeneration_steps,
    run_full_regeneration,
    run_extract_docx_step,
    run_extract_references_step,
    run_generate_transcripts_json_step,
    run_index_chromadb_json_step,
    run_regeneration_step,
)


router = APIRouter()


@contextmanager
def _temporary_env(overrides: dict[str, str | None]):
    previous: dict[str, str | None] = {}
    try:
        for key, value in overrides.items():
            previous[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@router.get("/api/database/steps")
def get_database_regeneration_steps():
    """List available regeneration steps."""
    return {"status": "ok", "steps": list_regeneration_steps()}


@router.post("/api/database/run-step")
def run_database_step(
    step: str = Query(..., description="Step key to run, e.g. generate_transcripts_json."),
):
    """Run one regeneration step by key."""
    result = run_regeneration_step(step)
    status_code = 200 if result.get("status") == "ok" else 400
    return JSONResponse(status_code=status_code, content=result)


@router.post("/api/database/extract-docx")
def run_extract_docx():
    """Run DOCX extraction step."""
    result = run_extract_docx_step()
    status_code = 200 if result.get("status") == "ok" else 500
    return JSONResponse(status_code=status_code, content=result)


@router.post("/api/database/extract-references")
def run_extract_references():
    """Run references extraction step."""
    result = run_extract_references_step()
    status_code = 200 if result.get("status") == "ok" else 500
    return JSONResponse(status_code=status_code, content=result)


@router.post("/api/database/generate-transcripts-json")
def run_generate_transcripts_json():
    """Run transcripts_chromadb.json generation step."""
    result = run_generate_transcripts_json_step()
    status_code = 200 if result.get("status") == "ok" else 500
    return JSONResponse(status_code=status_code, content=result)


@router.post("/api/database/index-chromadb-json")
def run_index_chromadb_json():
    """Run ChromaDB indexing step."""
    result = run_index_chromadb_json_step()
    status_code = 200 if result.get("status") == "ok" else 500
    return JSONResponse(status_code=status_code, content=result)


@router.post("/api/database/regenerate")
def regenerate_database(
    include_extract_docx: bool = Query(False, description="Run DOCX extraction before regeneration."),
    include_extract_references: bool = Query(False, description="Run references extraction before regeneration."),
    llm_provider: str | None = Query(None, description="Optional LLM provider override for this run."),
    embedding_provider: str | None = Query(None, description="Optional embedding provider override for this run."),
):
    """Run the full regeneration pipeline.

    Core steps mirror build-database.bat:
    - generate_transcripts_json
    - index_chromadb_json
    """
    env_overrides = {
        "LLM_PROVIDER": llm_provider,
        "EMBEDDING_PROVIDER": embedding_provider,
    }

    with _temporary_env(env_overrides):
        result = run_full_regeneration(
            include_extract_docx=include_extract_docx,
            include_extract_references=include_extract_references,
        )

    result["provider"] = {
        "llm_provider": llm_provider or os.getenv("LLM_PROVIDER", "vercel"),
        "embedding_provider": embedding_provider or os.getenv("EMBEDDING_PROVIDER", "vercel"),
    }

    status_code = 200 if result.get("status") == "success" else 500
    return JSONResponse(status_code=status_code, content=result)

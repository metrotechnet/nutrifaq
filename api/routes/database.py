"""Database regeneration routes.

Provides API endpoints to run the nutrifaq-dbase regeneration pipeline
using scripts under api/db_pipeline.
"""

import os

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from api.services.entra_auth_service import require_admin

from api.services.database_regeneration_service import (
    get_regeneration_status,
    list_regeneration_steps,
    request_regeneration_cancel,
    run_full_regeneration,
    run_extract_docx_step,
    run_extract_references_step,
    run_generate_transcripts_json_step,
    run_index_chromadb_json_step,
    run_regeneration_step,
)


router = APIRouter(dependencies=[Depends(require_admin)])


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
def regenerate_database():
    """Run the full regeneration pipeline.

    Core steps mirror build-database.bat:
    - generate_transcripts_json
    - index_chromadb_json
    """
    result = run_full_regeneration(
        include_extract_docx=True,
        include_extract_references=True,
    )

    result["provider"] = {
        "llm_provider": os.getenv("LLM_PROVIDER", "azure"),
        "embedding_provider": os.getenv("EMBEDDING_PROVIDER", "azure"),
    }

    status_value = result.get("status")
    if status_value in {"success", "cancelled"}:
        status_code = 200
    elif status_value == "busy":
        status_code = 409
    else:
        status_code = 500
    return JSONResponse(status_code=status_code, content=result)


@router.post("/api/database/regenerate/cancel")
def cancel_regeneration():
    """Request cancellation of the currently running regeneration job."""
    result = request_regeneration_cancel()
    status_code = 200 if result.get("status") in {"cancelling", "idle"} else 500
    return JSONResponse(status_code=status_code, content=result)


@router.get("/api/database/regenerate/status")
def regeneration_status():
    """Return current regeneration execution status."""
    return {"status": "ok", "regeneration": get_regeneration_status()}

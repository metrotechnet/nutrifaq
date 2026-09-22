"""Database regeneration routes.

Provides API endpoints to run the nutrifaq-dbase regeneration pipeline
using scripts under api/db_pipeline.
"""

import os

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from api.services.entra_auth_service import require_admin

from api.services.database_regeneration_service import (
    generate_questions_from_transcripts_json,
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


@router.post("/api/database/generate-questions")
def generate_questions(
    question_count: int = Query(default=3, ge=1, le=20, description="Number of questions to generate per document."),
    source_root_folder: str | None = Query(
        default=None,
        description="Optional local KB folder to read transcripts_chromadb.json from.",
    ),
    debug_container: str | None = Query(
        default=None,
        description="Optional debug blob container override for output upload.",
    ),
    debug_root_folder: str | None = Query(
        default=None,
        description="Optional debug blob root folder (prefix) override for output upload.",
    ),
):
    """Generate per-document questions from transcripts JSON and upload the result to debug blob storage."""
    result = generate_questions_from_transcripts_json(
        question_count=question_count,
        source_root_folder=source_root_folder,
        target_container_name=debug_container,
        target_root_folder=debug_root_folder,
    )
    status_code = 200 if result.get("status") == "ok" else 500
    return JSONResponse(status_code=status_code, content=result)


@router.post("/api/database/regenerate")
def regenerate_database(
    root_folder: str | None = Query(
        default=None,
        description="Optional blob root folder (prefix). If omitted, debug prefix is used.",
    ),
    container: str | None = Query(
        default=None,
        description="Optional blob container name. If omitted, debug container is used.",
    ),
):
    """Run the full regeneration pipeline.

    Core steps mirror build-database.bat:
    - generate_transcripts_json
    - index_chromadb_json
    """
    result = run_full_regeneration(
        include_extract_docx=True,
        include_extract_references=True,
        root_folder=root_folder,
        container_name=container,
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

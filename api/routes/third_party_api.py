"""Third-party API routes exposing external query access."""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from api.routes.query import _query_agent_response
from api.schemas.models import QueryRequest
from api.services.entra_auth_service import require_client_or_query_key
from api.services.download_service import require_transfer_key, save_uploaded_file

router = APIRouter()


@router.post("/query", dependencies=[Depends(require_client_or_query_key)])
async def query_agent(request: Request, query_request: QueryRequest, chroma_db_path: str | None = None):
    """Main external query endpoint with Entra-or-key authentication."""
    return _query_agent_response(request, query_request, debug_mode=False, chroma_db_path=chroma_db_path)


@router.post("/download_page", dependencies=[Depends(require_transfer_key)])
async def download_page(file: UploadFile = File(...)):
    """Receive a third-party file and persist it in nutrifaq-dbase-main/documents."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file.")

    return save_uploaded_file(file.filename, content)

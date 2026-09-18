"""
Agent Configuration API Routes

This module defines endpoints for retrieving agent configuration in the Nutrifaq Agent backend.
"""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from typing import Optional

from api.services.config import get_config
from api.services.query_chromadb import check_remote_chromadb_connection

router = APIRouter()



@router.get("/api/get_config")
def get_config_endpoint():
    """
    Retrieve the configuration for the Nutrifaq Agent (single-agent deployment).

    Returns:
        dict: The merged configuration dictionary for the agent.
    """
    return get_config()


@router.get("/api/db/connection")
def get_db_connection_status(
    project_name: Optional[str] = None,
    collection_name: Optional[str] = None,
):
    """Return remote ChromaDB connection status for the current API configuration."""
    result = check_remote_chromadb_connection(
        project_name=project_name,
        collection_name=collection_name,
    )
    status_code = 200 if result.get("status") == "ok" else 503
    return JSONResponse(status_code=status_code, content=result)

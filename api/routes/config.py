"""
Agent Configuration API Routes

This module defines endpoints for retrieving agent configuration in the Nutrifaq Agent backend.
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from typing import Optional

from api.services.entra_auth_service import require_collaborator
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


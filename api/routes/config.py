"""
Agent Configuration API Routes

This module defines endpoints for retrieving agent configuration in the Nutrifaq Agent backend.
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from typing import Optional

from api.services.entra_auth_service import require_collaborator
from api.services.config import get_config
from api.services.model_catalog import load_accessible_models
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


@router.get("/api/models")
def get_models_endpoint():
    """Return the list of frontend-selectable chat models."""
    try:
        payload = load_accessible_models()
        return {
            "status": "ok",
            **payload,
        }
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Unable to load model catalog: {exc}",
            },
        )


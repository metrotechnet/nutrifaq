"""
Agent Configuration API Routes

This module defines endpoints for retrieving agent configuration in the Nutria Agent backend.
"""
from fastapi import APIRouter, Query
from typing import Optional

from api.config import get_config

router = APIRouter()



@router.get("/api/get_config")
def get_config_endpoint():
    """
    Retrieve the configuration for the Nutria Agent (single-agent deployment).

    Returns:
        dict: The merged configuration dictionary for the agent.
    """
    return get_config()

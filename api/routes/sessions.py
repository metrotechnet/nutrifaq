"""
Session Management API Routes

This module defines endpoints for managing conversation sessions in the Nutria Agent backend.
"""
from fastapi import APIRouter

from api.sessions import reset_session, get_session_info

router = APIRouter()



@router.post("/api/reset_session")
def reset_session_endpoint(session_id: str = None):
    """
    Reset a conversation session by session ID.

    Args:
        session_id (str, optional): The session ID to reset. If None, no session is reset.

    Returns:
        dict: Status and message about the reset operation.
    """
    return reset_session(session_id)



@router.get("/api/session_info")
def get_session_info_endpoint(session_id: str):
    """
    Get information about a conversation session.

    Args:
        session_id (str): The session ID to retrieve info for.

    Returns:
        dict: Session information (exists, message count, timestamps, etc.).
    """
    return get_session_info(session_id)

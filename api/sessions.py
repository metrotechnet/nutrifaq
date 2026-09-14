"""
Session Management Utilities

This module provides functions for managing conversation sessions in the Nutria Agent backend.
"""
from datetime import datetime, timedelta
from typing import Dict
import uuid

# Session storage
conversation_sessions: Dict[str, Dict] = {}
SESSION_TIMEOUT = timedelta(hours=2)


def clean_old_sessions():
    """
    Delete expired conversation sessions from the in-memory session store.
    """
    now = datetime.now()
    expired_sessions = [
        sid for sid, session in conversation_sessions.items()
        if now - session['last_activity'] > SESSION_TIMEOUT
    ]
    for sid in expired_sessions:
        del conversation_sessions[sid]


def get_or_create_session(session_id: str = None) -> tuple[str, dict]:
    """
    Retrieve an existing session or create a new one if not found.

    Args:
        session_id (str, optional): The session ID to retrieve or create. If None, a new session is created.

    Returns:
        tuple: (session_id, session_dict)
    """
    if not session_id:
        session_id = str(uuid.uuid4())
    
    clean_old_sessions()
    
    if session_id not in conversation_sessions:
        conversation_sessions[session_id] = {
            'messages': [],
            'created_at': datetime.now(),
            'last_activity': datetime.now(),
            'links': {},  # question_id -> link list
            'refusals': set(),  # question_ids that were refused
        }
    
    session = conversation_sessions[session_id]
    
    # Ensure links dict exists for backward compatibility
    if 'links' not in session:
        session['links'] = {}
    
    # Ensure refusals set exists for backward compatibility
    if 'refusals' not in session:
        session['refusals'] = set()
    
    session['last_activity'] = datetime.now()
    
    return session_id, session


def reset_session(session_id: str = None):
    """
    Reset a conversation session by session ID.

    Args:
        session_id (str, optional): The session ID to reset.

    Returns:
        dict: Status and message about the reset operation.
    """
    if session_id and session_id in conversation_sessions:
        del conversation_sessions[session_id]
        return {"status": "success", "message": "Session reset"}
    return {"status": "info", "message": "No active session to reset"}


def get_session_info(session_id: str):
    """
    Get information about a conversation session.

    Args:
        session_id (str): The session ID to retrieve info for.

    Returns:
        dict: Session information (exists, message count, timestamps, etc.).
    """
    if session_id in conversation_sessions:
        session = conversation_sessions[session_id]
        return {
            "exists": True,
            "message_count": len(session['messages']),
            "created_at": session['created_at'].isoformat(),
            "last_activity": session['last_activity'].isoformat()
        }
    return {"exists": False}


def is_session_rate_limited(session_id: str, max_requests_per_hour: int = 50) -> bool:
    """
    Check if a session has exceeded rate limit.
    
    Args:
        session_id: Session ID to check
        max_requests_per_hour: Maximum requests allowed per hour (default: 50)
        
    Returns:
        True if rate limited, False otherwise
    """
    if not session_id or session_id not in conversation_sessions:
        return False
    
    session = conversation_sessions[session_id]
    messages = session.get('messages', [])
    
    # Count user messages in the last hour
    now = datetime.now()
    one_hour_ago = now - timedelta(hours=1)
    
    recent_user_messages = [
        msg for msg in messages
        if msg.get('role') == 'user' and 
        datetime.fromisoformat(msg['timestamp']) > one_hour_ago
    ]
    
    return len(recent_user_messages) >= max_requests_per_hour

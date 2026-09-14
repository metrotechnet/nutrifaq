"""
API Data Models

This module defines Pydantic models for request validation in the Nutria Agent backend.
"""
from pydantic import BaseModel
from typing import Optional



class QueryRequest(BaseModel):
    """
    Model for user query requests to the agent.
    """
    question: str
    agent: str = "agent"
    language: str = "fr"
    timezone: str = "UTC"
    locale: str = "fr-FR"
    session_id: Optional[str] = None



class TranslateRequest(BaseModel):
    """
    Model for translation requests (text or audio).
    """
    text: str
    target_language: str = "en"
    source_language: str = "auto"

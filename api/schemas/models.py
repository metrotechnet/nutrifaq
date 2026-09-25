"""API data models."""

from typing import Optional

from pydantic import BaseModel


class QueryRequest(BaseModel):
    """Model for user query requests to the agent."""

    question: str
    agent: str = "agent"
    language: str = "fr"
    timezone: str = "UTC"
    locale: str = "fr-FR"
    llm_model: Optional[str] = None
    provider: Optional[str] = None
    session_id: Optional[str] = None


class TranslateRequest(BaseModel):
    """Model for translation requests (text or audio)."""

    text: str
    target_language: str = "en"
    source_language: str = "auto"


class BlobContainerCopyRequest(BaseModel):
    """Model for copying blobs between two containers."""

    source_container: str
    destination_container: str
    source_prefix: Optional[str] = None
    destination_prefix: Optional[str] = None
    overwrite: bool = True
    wait_for_completion: bool = True
    timeout_seconds: int = 120

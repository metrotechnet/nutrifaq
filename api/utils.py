"""
Utility Functions for API

This module provides helper functions and constants for use in Nutria Agent API routes.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
QUESTION_LOG_PATH = PROJECT_ROOT / "question_log.json"

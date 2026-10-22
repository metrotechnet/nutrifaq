"""
Logging Utilities

This module provides functions for logging questions, responses, comments, and likes in the Nutrifaq Agent backend.
"""
from pathlib import Path
from datetime import datetime
import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent
DEFAULT_DEBUG_KB_ROOT = REPO_ROOT / "nutrifaq-dbase-main"
QUESTION_LOG_PATH = DEFAULT_DEBUG_KB_ROOT / "question_log.json"
question_log_lock = threading.Lock()


def configure_logging() -> Path:
    """Configure a single file log sink for the application and scripts."""
    configured_path = os.getenv("LOG_FILE_PATH", "logs/nutrifaq.log").strip()
    if not configured_path:
        configured_path = "logs/nutrifaq.log"

    log_path = Path(configured_path)
    if not log_path.is_absolute():
        log_path = (REPO_ROOT / log_path).resolve()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    file_handler_exists = any(
        isinstance(handler, logging.FileHandler) and getattr(handler, "baseFilename", None) == str(log_path)
        for handler in root_logger.handlers
    )
    if not file_handler_exists:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root_logger.addHandler(file_handler)

    stream_handler_exists = any(
        isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
        for handler in root_logger.handlers
    )
    if not stream_handler_exists:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root_logger.addHandler(stream_handler)

    return log_path

GCS_LOG_BLOB_NAME = "question_log.json"


def contains_medical_disclaimer(response_text):
    """
    Detect if a response contains phrases suggesting to consult a professional.
    Returns True if a medical disclaimer is present (no links should be shown).

    Args:
        response_text (str): The response text to check.

    Returns:
        bool: True if a disclaimer is present, False otherwise.
    """
    if not response_text:
        return False
    
    response_lower = response_text.lower()
    
    # French patterns
    french_patterns = [
        'je ne peux pas répondre',
        'je ne peux pas répondre à cette question',
        'consulter un professionnel',
        'consulte un professionnel',
        'consultez un professionnel',
        'consulter votre médecin',
        'consultez votre médecin',
        'parler à un médecin',
        'parlez à un médecin',
        'voir un médecin',
        'voyez un médecin',
        'demander conseil à un professionnel',
        'demandez conseil à un professionnel',
        'avis médical',
        'consultation médicale',
        'professionnel de santé',
        'professionnel de la santé',
        'nutritionniste',
        'diététicien',
    ]
    
    # English patterns
    english_patterns = [
        'i cannot answer',
        'i cannot answer this question',
        'consult a professional',
        'consult your doctor',
        'see a doctor',
        'talk to a doctor',
        'speak to a doctor',
        'seek medical advice',
        'medical consultation',
        'health professional',
        'healthcare professional',
        'nutritionist',
        'dietitian',
    ]
    
    all_patterns = french_patterns + english_patterns
    
    # Check if at least one pattern is present
    for pattern in all_patterns:
        if pattern in response_lower:
            return True
    
    return False


def save_question_response(question_id, question, response, model_used=None):
    """
    Save a question and its response to GCS.

    Args:
        question_id (str): The unique ID of the question.
        question (str): The question text.
        response (str): The agent's response.
        model_used (str | None): The LLM model used to generate the answer.
    """
    entry = {
        "question_id": question_id,
        "question": question,
        "response": response,
        "model_used": model_used,
        "timestamp": datetime.now().isoformat(),
        "comments": []
    }
    with question_log_lock:
        data = _download_log_from_gcs()
        data.append(entry)
        _upload_log_to_gcs(data)


def reset_question_log():
    """Reset the persisted question log for the current user session."""
    empty_data = []
    with question_log_lock:
        _upload_log_to_gcs(empty_data)
    return empty_data


def _upload_log_to_gcs(data):
    """Upload question log data to GCS bucket (server) or local file (local dev)."""
    if not os.getenv("K_SERVICE"):
        QUESTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(QUESTION_LOG_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return
    try:
        from google.cloud import storage
        gcs_path = os.getenv("GCS_BUCKET_NAME")
        if not gcs_path:
            logger.warning("[GCS Upload] GCS_BUCKET_NAME not set, skipping upload")
            return
        # Support "bucket/prefix" format in GCS_BUCKET_NAME
        parts = gcs_path.strip().split("/", 1)
        bucket_name = parts[0]
        prefix = parts[1] + "/" if len(parts) > 1 else ""
        blob_path = f"{prefix}{GCS_LOG_BLOB_NAME}"
        logger.info("[GCS Upload] Uploading to gs://%s/%s (%s entries)", bucket_name, blob_path, len(data))
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(
            json.dumps(data, ensure_ascii=False, indent=2),
            content_type="application/json"
        )
        logger.info("[GCS Upload] Success")
    except Exception as e:
        import logging as std_logging
        std_logging.getLogger(__name__).error(f"Failed to upload log to GCS: {e}")


def _download_log_from_gcs():
    """Download question log from GCS bucket (server) or local file (local dev)."""
    if not os.getenv("K_SERVICE"):
        try:
            if QUESTION_LOG_PATH.exists():
                with open(QUESTION_LOG_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return []
    try:
        from google.cloud import storage
        gcs_path = os.getenv("GCS_BUCKET_NAME")
        if not gcs_path:
            logger.warning("[GCS Download] GCS_BUCKET_NAME not set")
            return []
        parts = gcs_path.strip().split("/", 1)
        bucket_name = parts[0]
        prefix = parts[1] + "/" if len(parts) > 1 else ""
        blob_path = f"{prefix}{GCS_LOG_BLOB_NAME}"
        logger.info("[GCS Download] Downloading gs://%s/%s", bucket_name, blob_path)
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        if not blob.exists():
            logger.warning("[GCS Download] Blob not found")
            return []
        data = json.loads(blob.download_as_text())
        logger.info("[GCS Download] Success (%s entries)", len(data))
        return data
    except Exception as e:
        import logging as std_logging
        std_logging.getLogger(__name__).error(f"Failed to download log from GCS: {e}")
        return []


def add_comment_to_question(question_id, comment):
    """
    Add a comment to a question by its identifier.
    """
    with question_log_lock:
        data = _download_log_from_gcs()
        if not data:
            return False
        for entry in data:
            if entry.get("question_id") == question_id:
                entry["comments"] = [{
                    "comment": comment,
                    "timestamp": datetime.now().isoformat()
                }]
                _upload_log_to_gcs(data)
                return True
        return False


def add_like_to_question(question_id: str, like: bool):
    """Add or update a like/dislike vote for a question. Replaces any previous vote."""
    with question_log_lock:
        data = _download_log_from_gcs()
        if not data:
            return {"status": "error", "message": "Log not found"}
        for entry in data:
            if entry.get("question_id") == question_id:
                entry["likes"] = {
                    "like": like,
                    "timestamp": datetime.now().isoformat()
                }
                _upload_log_to_gcs(data)
                return {"status": "success", "message": "Vote recorded"}
        return {"status": "error", "message": "Question ID not found"}

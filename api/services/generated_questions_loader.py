"""Load generated questions from local debug knowledge-base JSON."""

from __future__ import annotations

import json
from pathlib import Path

from api.services.query_chromadb import get_debug_local_kb_root_folder

REPO_ROOT = Path(__file__).resolve().parents[2]


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _resolve_generated_questions_path(kb_root_folder: str | None = None) -> Path:
    root_folder = (kb_root_folder or get_debug_local_kb_root_folder()).strip("/")
    return REPO_ROOT / root_folder / "generated_questions.json"


def load_generated_questions(kb_root_folder: str | None = None) -> dict:
    """Read generated_questions.json and return document-grouped question data."""
    generated_questions_path = _resolve_generated_questions_path(kb_root_folder)
    if not generated_questions_path.exists():
        return {
            "documents": [],
            "count_documents": 0,
            "count_questions": 0,
            "message": f"File not found: {generated_questions_path}",
        }

    with generated_questions_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    source_documents = payload.get("documents") if isinstance(payload, dict) else []
    if not isinstance(source_documents, list):
        source_documents = []

    grouped: list[dict] = []
    question_total = 0
    for index, doc in enumerate(source_documents):
        if not isinstance(doc, dict):
            continue

        title = str(doc.get("source") or doc.get("topic") or doc.get("document_id") or f"Document {index + 1}").strip()
        questions_raw = doc.get("questions")
        questions = []
        if isinstance(questions_raw, list):
            questions = [str(item).strip() for item in questions_raw if str(item).strip()]

        question_total += len(questions)
        grouped.append(
            {
                "document_title": title,
                "document_id": doc.get("document_id"),
                "questions": questions,
            }
        )

    return {
        "documents": grouped,
        "count_documents": len(grouped),
        "count_questions": question_total,
    }
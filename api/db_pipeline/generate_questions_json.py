"""
Generate generated_questions.json from reviewed_documents.json.

Usage:
    python generate_questions_json.py <knowledge_base_path> [question_count]
"""

import json
import logging
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / ".env", override=False)

from api.services.logging import configure_logging  # noqa: E402
from api.services.llm_service import create_chat_completion_text, get_gateway_client  # noqa: E402
from api.services.database_regeneration_service import _write_progress_snapshot  # noqa: E402

configure_logging()


def _new_file_only_enabled() -> bool:
    return os.getenv("NUTRIFAQ_PROCESS_ONLY_NEW_FILES", "").strip().lower() in {"1", "true", "yes", "on"}


def _pipeline_state_path(kb_root: Path) -> Path:
    return kb_root / ".pipeline_new_files_state.json"


def _load_pipeline_state(kb_root: Path) -> dict:
    state_path = _pipeline_state_path(kb_root)
    if not state_path.exists():
        return {}
    try:
        with state_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_pipeline_state(kb_root: Path, payload: dict) -> None:
    state_path = _pipeline_state_path(kb_root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _sanitize_question_topic(text: str, *, max_words: int = 8) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return "ce document"

    sentence = re.split(r"[\.!?\n]", normalized, maxsplit=1)[0].strip()
    source = sentence or normalized
    words = source.split()
    short = " ".join(words[:max_words]).strip(" ,;:-")
    return short if short else "ce document"


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _extract_json_array_from_text(text: str) -> list[str]:
    if not text:
        return []

    stripped = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    candidate = fence_match.group(1) if fence_match else stripped

    if not fence_match:
        bracket_match = re.search(r"\[.*\]", candidate, flags=re.DOTALL)
        if bracket_match:
            candidate = bracket_match.group(0)

    try:
        payload = json.loads(candidate)
    except Exception:
        return []

    if not isinstance(payload, list):
        return []

    return [str(item).strip() for item in payload if isinstance(item, (str, int, float)) and str(item).strip()]


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _build_llm_prompt(text_excerpt: str, topic: str, question_count: int) -> str:
    return (
        "Tu es un assistant de creation de jeux de questions en nutrition. "
        "Genere exactement {count} questions pertinentes sur la nutrition en general. "
        "Retourne uniquement un tableau JSON valide de chaines, sans markdown, sans texte additionnel.\n\n"
        "Sujet detecte: {topic}\n"
        "Extrait du document:\n{text}\n\n"
        "Contraintes:\n"
        "- Questions en francais.\n"
        "- Une question par element du tableau.\n"
        "- Pas de numerotation ni prefixe.\n"
        "- Questions claires, actionnables et utiles au grand public.\n"
        "- Les questions doivent porter sur la nutrition en general, pas sur des points trop specifiques au texte fourni."
    ).format(count=question_count, topic=topic, text=text_excerpt)


# Purpose: Internal helper used to keep the main workflow readable and maintainable.
# Inputs/Outputs: See signature and return annotation for contract details.
def _load_reviewed_payload(reviewed_path: Path) -> dict:
    try:
        raw = reviewed_path.read_text(encoding="utf-8")
    except Exception as exc:
        raise RuntimeError(f"Unable to read input file: {reviewed_path} ({exc})") from exc

    if not raw.strip():
        raise RuntimeError(
            f"Input file is empty: {reviewed_path}. "
            "Generate reviewed_documents.json before running question generation."
        )

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON in {reviewed_path}: line {exc.lineno}, column {exc.colno}. "
            "Generate reviewed_documents.json and retry."
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid JSON root in {reviewed_path}: expected an object.")

    return payload


# Purpose: Implement a focused unit of backend behavior used by routes or services.
# Inputs/Outputs: See signature and return annotation for contract details.
def generate_questions_json(kb_root: Path, question_count: int = 3, llm_model: str | None = None) -> Path:
    reviewed_path = kb_root / "reviewed_documents.json"
    if not reviewed_path.exists():
        raise FileNotFoundError(f"Missing input file: {reviewed_path}")

    payload = _load_reviewed_payload(reviewed_path)

    documents = payload.get("documents", []) if isinstance(payload, dict) else []
    if not isinstance(documents, list) or not documents:
        raise RuntimeError("No documents found in reviewed_documents.json")
    if _new_file_only_enabled():
        state = _load_pipeline_state(kb_root)
        allowed = set(state.get("review_document_text", {}).keys())
        if allowed:
            documents = [
                doc for doc in documents
                if isinstance(doc, dict)
                and str(doc.get("filename") or doc.get("metadata", {}).get("filename") or doc.get("id") or "").strip() in allowed
            ]

    resolved_model = (llm_model or os.getenv("VERCEL_CHAT_DEPLOYMENT") or os.getenv("CHAT_MODEL") or os.getenv("LLM_MODEL") or "").strip()
    if not resolved_model:
        raise RuntimeError("No model was provided by the client for question generation.")

    client = get_gateway_client()
    generated_documents = []
    llm_failures = 0
    total_documents = len(documents)
    _write_progress_snapshot("generate_questions", 0, total_documents, "files")

    processed_documents = 0
    for doc in documents:
        try:
            if not isinstance(doc, dict):
                logger.info("Skipping invalid question-generation entry %s/%s", processed_documents + 1, total_documents)
                continue

            doc_id = str(doc.get("id", "unknown"))
            metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
            source_name = str(metadata.get("title") or doc_id)
            full_text = str(doc.get("text", ""))
            logger.info("Generating questions for document %s/%s: %s", processed_documents + 1, total_documents, source_name)
            topic = _sanitize_question_topic(full_text)
            text_excerpt = re.sub(r"\s+", " ", full_text).strip()[:2200]

            llm_questions = []
            llm_error = None
            try:
                prompt = _build_llm_prompt(text_excerpt, topic, question_count)
                raw_output = create_chat_completion_text(
                    client=client,
                    model_name=resolved_model,
                    prompt=prompt,
                    temperature=0.4,
                )
                llm_questions = _extract_json_array_from_text(raw_output)
            except Exception as exc:
                llm_error = str(exc)

            if len(llm_questions) < question_count:
                raise RuntimeError(
                    f"Model did not return enough questions for {doc_id}: expected {question_count}, got {len(llm_questions)}."
                )

            questions = llm_questions[:question_count]
            generation_mode = "llm"

            generated_documents.append(
                {
                    "document_id": doc_id,
                    "source": source_name,
                    "topic": topic,
                    "questions": questions,
                    "generation_mode": generation_mode,
                    "llm_error": llm_error,
                }
            )
            logger.info("Generated %d questions for %s", len(questions), source_name)
            time.sleep(0.05)
        finally:
            processed_documents += 1
            _write_progress_snapshot("generate_questions", processed_documents, total_documents, "files")

    output_data = {
        "status": "ok",
        "question_count_per_document": question_count,
        "total_documents": len(generated_documents),
        "generated_from": str(reviewed_path),
        "llm_failures": llm_failures,
        "documents": generated_documents,
    }

    if _new_file_only_enabled():
        state = _load_pipeline_state(kb_root)
        state["generate_questions"] = {
            str(doc.get("document_id") or doc.get("source") or ""): True
            for doc in generated_documents
            if isinstance(doc, dict)
        }
        _save_pipeline_state(kb_root, state)

    output_path = kb_root / "generated_questions.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(output_data, handle, ensure_ascii=False, indent=2)

    return output_path


# Purpose: Implement a focused unit of backend behavior used by routes or services.
# Inputs/Outputs: See signature and return annotation for contract details.
def main() -> int:
    if len(sys.argv) not in {2, 3}:
        logger.error("Usage: python generate_questions_json.py <knowledge_base_path> [question_count]")
        return 1

    kb_root = Path(sys.argv[1])
    if not kb_root.exists():
        logger.error("Directory not found: %s", kb_root)
        return 1

    try:
        question_count = int(sys.argv[2]) if len(sys.argv) == 3 else 3
    except ValueError:
        logger.error("question_count must be an integer.")
        return 1

    if question_count < 1:
        logger.error("question_count must be >= 1")
        return 1

    try:
        output_path = generate_questions_json(kb_root=kb_root, question_count=question_count)
        logger.info("Generated questions file: %s", output_path)
        return 0
    except Exception as exc:
        logger.exception("Error generating questions: %s", exc)
        return 1


if __name__ == "__main__":
    exit_code = main()
    # Avoid debugger interruptions on expected non-zero exits.
    if sys.gettrace() is None and exit_code != 0:
        raise SystemExit(exit_code)




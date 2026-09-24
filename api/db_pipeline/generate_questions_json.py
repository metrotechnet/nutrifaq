"""
Generate generated_questions.json from transcripts_chromadb.json.

Usage:
    python generate_questions_json.py <knowledge_base_path> [question_count]
"""

import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.services.llm_service import create_chat_completion_text, get_gateway_client  # noqa: E402
from api.services.database_regeneration_service import _write_progress_snapshot  # noqa: E402


def _sanitize_question_topic(text: str, *, max_words: int = 8) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return "ce document"

    sentence = re.split(r"[\.!?\n]", normalized, maxsplit=1)[0].strip()
    source = sentence or normalized
    words = source.split()
    short = " ".join(words[:max_words]).strip(" ,;:-")
    return short if short else "ce document"


def _build_questions_fallback(topic: str, question_count: int) -> list[str]:
    templates = [
        "Quels sont les points cles de {topic} ?",
        "Quelles recommandations pratiques ressortent de {topic} ?",
        "Quels risques ou limites sont mentionnes dans {topic} ?",
        "Comment appliquer les informations de {topic} au quotidien ?",
        "Quels elements sont les plus importants a retenir sur {topic} ?",
        "Quelles questions restent ouvertes concernant {topic} ?",
    ]
    return [templates[idx % len(templates)].format(topic=topic) for idx in range(question_count)]


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


def _load_transcripts_payload(transcripts_path: Path) -> dict:
    try:
        raw = transcripts_path.read_text(encoding="utf-8")
    except Exception as exc:
        raise RuntimeError(f"Unable to read input file: {transcripts_path} ({exc})") from exc

    if not raw.strip():
        raise RuntimeError(
            f"Input file is empty: {transcripts_path}. "
            "Regenerate transcripts_chromadb.json before running question generation."
        )

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON in {transcripts_path}: line {exc.lineno}, column {exc.colno}. "
            "Regenerate transcripts_chromadb.json and retry."
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid JSON root in {transcripts_path}: expected an object.")

    return payload


def generate_questions_json(kb_root: Path, question_count: int = 3) -> Path:
    transcripts_path = kb_root / "transcripts_chromadb.json"
    if not transcripts_path.exists():
        raise FileNotFoundError(f"Missing input file: {transcripts_path}")

    payload = _load_transcripts_payload(transcripts_path)

    documents = payload.get("documents", []) if isinstance(payload, dict) else []
    if not isinstance(documents, list) or not documents:
        raise RuntimeError("No documents found in transcripts_chromadb.json")

    client = get_gateway_client()
    generated_documents = []
    llm_failures = 0
    total_documents = len(documents)
    _write_progress_snapshot("generate_questions", 0, total_documents, "files")

    processed_documents = 0
    for doc in documents:
        try:
            if not isinstance(doc, dict):
                continue

            doc_id = str(doc.get("id", "unknown"))
            metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
            source_name = str(metadata.get("source") or metadata.get("reference") or doc_id)
            full_text = str(doc.get("text", ""))
            topic = _sanitize_question_topic(full_text)
            text_excerpt = re.sub(r"\s+", " ", full_text).strip()[:2200]

            llm_questions = []
            llm_error = None
            try:
                prompt = _build_llm_prompt(text_excerpt, topic, question_count)
                raw_output = create_chat_completion_text(
                    client=client,
                    model_name=None,
                    prompt=prompt,
                    temperature=0.4,
                )
                llm_questions = _extract_json_array_from_text(raw_output)
            except Exception as exc:
                llm_error = str(exc)

            if len(llm_questions) < question_count:
                llm_failures += 1
                questions = (llm_questions + _build_questions_fallback(topic, question_count))[:question_count]
                generation_mode = "fallback"
            else:
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
            time.sleep(0.05)
        finally:
            processed_documents += 1
            _write_progress_snapshot("generate_questions", processed_documents, total_documents, "files")

    output_data = {
        "status": "ok",
        "question_count_per_document": question_count,
        "total_documents": len(generated_documents),
        "generated_from": str(transcripts_path),
        "llm_failures": llm_failures,
        "documents": generated_documents,
    }

    output_path = kb_root / "generated_questions.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(output_data, handle, ensure_ascii=False, indent=2)

    return output_path


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        print("Usage: python generate_questions_json.py <knowledge_base_path> [question_count]")
        return 1

    kb_root = Path(sys.argv[1])
    if not kb_root.exists():
        print(f"Directory not found: {kb_root}")
        return 1

    try:
        question_count = int(sys.argv[2]) if len(sys.argv) == 3 else 3
    except ValueError:
        print("question_count must be an integer.")
        return 1

    if question_count < 1:
        print("question_count must be >= 1")
        return 1

    try:
        output_path = generate_questions_json(kb_root=kb_root, question_count=question_count)
        print(f"Generated questions file: {output_path}")
        return 0
    except Exception as exc:
        print(f"Error generating questions: {exc}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    # Avoid debugger interruptions on expected non-zero exits.
    if sys.gettrace() is None and exit_code != 0:
        raise SystemExit(exit_code)




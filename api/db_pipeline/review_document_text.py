"""
Review extracted document text and keep only relevant nutrition content.

Usage:
    python review_document_text.py <knowledge_base_path>
"""

import json
import logging
import os
import re
import sys
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


def _extract_json_object(text: str) -> dict:
    if not text:
        return {}

    stripped = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    candidate = fence_match.group(1) if fence_match else stripped

    if not fence_match:
        brace_match = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
        if brace_match:
            candidate = brace_match.group(0)

    try:
        payload = json.loads(candidate)
    except Exception:
        return {}

    if not isinstance(payload, dict):
        return {}

    return payload


def _build_review_prompt(text: str) -> str:
    preview = re.sub(r"\s+", " ", text or "").strip()
    preview = preview[:8500]

    return (
        "Tu es un assistant de filtration de contenus pour une base de connaissances en nutrition.\n"
        "Analyse le texte suivant et décide s'il contient du contenu pertinent pour l'enseignement de la nutrition ou s'il s'agit surtout de texte de navigation/structure de site web.\n\n"
        "Retourne uniquement un objet JSON valide avec cette forme exacte :\n"
        "{\n"
        "  \"relevant\": true|false,\n"
        "  \"reason\": \"courte explication\",\n"
        "  \"key_points\": [\"point clé 1\", \"point clé 2\", \"point clé 3\"]\n"
        "}\n\n"
        "Règles:\n"
        "- Le contenu pertinent correspond à des informations utiles, factuelles, pédagogiques, cliniques ou nutritionnelles.\n"
        "- Considère comme non pertinent le texte de navigation, les menus, les liens, les bannières, les breadcrumbs, les appels à l'action, les titres de pages, les listes de liens, les blocs 'À lire aussi', les éléments de footer et tout contenu purement structurel.\n"
        "- Si le texte est trop court, vague, fragmentaire ou uniquement navigatoire, mets 'relevant' à false.\n"
        "- Si pertinent, donne entre 2 et 5 points clés, en français, très concis et précis.\n"
        "- Si non pertinent, mets une liste vide pour 'key_points'.\n"
        "- Ne retourne aucun texte hors du JSON.\n\n"
        "Texte à analyser:\n"
        f"{preview}"
    )


def _normalize_key_points(value):
    if not isinstance(value, list):
        return []

    points = []
    for item in value:
        cleaned = str(item).strip()
        if cleaned:
            points.append(cleaned)
    return points[:5]


def _load_reference_documents(kb_dir: Path):
    references_path = kb_dir / "references.json"
    if not references_path.exists():
        return []

    try:
        with references_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Could not load references.json: %s", exc)
        return []

    documents = payload.get("documents", []) if isinstance(payload, dict) else []
    if not isinstance(documents, list):
        return []
    return documents


def review_document_text(kb_dir: Path, llm_model: str | None = None):
    """Review extracted documents and keep only nutrition content for embedding."""
    logger.info("Reviewing extracted document text for relevance...")

    docs = _load_reference_documents(kb_dir)
    if not docs:
        logger.warning("No document payload found in references.json")
        output_path = kb_dir / "reviewed_documents.json"
        payload = {"total_documents": 0, "documents": []}
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    client = get_gateway_client()
    selected_model = (llm_model or os.getenv("VERCEL_CHAT_DEPLOYMENT") or os.getenv("CHAT_MODEL") or os.getenv("LLM_MODEL") or "").strip()
    if not selected_model:
        raise RuntimeError("No model was provided for review_document_text. Pass llm_model or set the configured model environment variable.")
    reviewed_documents = []
    total_documents = len(docs)
    _write_progress_snapshot("review_document_text", 0, total_documents, "files")

    for index, doc in enumerate(docs, start=1):
        try:
            if not isinstance(doc, dict):
                continue

            metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
            original_text = str(doc.get("text", "") or "")
            filename = str(doc.get("filename") or metadata.get("filename") or metadata.get("source_file") or f"doc_{index}")

            if not original_text.strip():
                reviewed_documents.append(
                    {
                        "filename": filename,
                        "relevant": False,
                        "reason": "Texte vide.",
                        "key_points": [],
                        "text": "",
                        "metadata": metadata,
                    }
                )
                _write_progress_snapshot("review_document_text", index, total_documents, "files")
                continue

            prompt = _build_review_prompt(original_text)
            raw_output = create_chat_completion_text(
                client=client,
                model_name=selected_model,
                prompt=prompt,
                temperature=0.2,
            )
            parsed = _extract_json_object(raw_output)
            relevant = bool(parsed.get("relevant", False))
            reason = str(parsed.get("reason") or "")
            key_points = _normalize_key_points(parsed.get("key_points"))
            final_text = original_text.strip() if relevant else ""

            reviewed_documents.append(
                {
                    "filename": filename,
                    "relevant": relevant,
                    "reason": reason,
                    "key_points": key_points,
                    "text": final_text,
                    "metadata": metadata,
                }
            )
        except Exception as exc:
            logger.exception("Failed to review document %s: %s", doc.get("filename", "unknown"), exc)
            reviewed_documents.append(
                {
                    "filename": str(doc.get("filename") or f"doc_{index}"),
                    "relevant": False,
                    "reason": f"Erreur de review: {exc}",
                    "key_points": [],
                    "text": "",
                    "metadata": doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {},
                }
            )
        finally:
            _write_progress_snapshot("review_document_text", index, total_documents, "files")

    payload = {
        "total_documents": len(reviewed_documents),
        "documents": reviewed_documents,
        "reviewed_at": __import__("datetime").datetime.now().isoformat(),
        "llm_model": selected_model,
    }

    output_path = kb_dir / "reviewed_documents.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved reviewed document analysis to %s", output_path)
    return payload


def main() -> None:
    kb_dir = Path(sys.argv[1]).resolve() if len(sys.argv) >= 2 and sys.argv[1].strip() else Path(__file__).resolve().parents[2] / "nutrifaq-dbase"
    llm_model = sys.argv[2].strip() if len(sys.argv) >= 3 and sys.argv[2].strip() else None
    review_document_text(kb_dir, llm_model=llm_model)


if __name__ == "__main__":
    main()

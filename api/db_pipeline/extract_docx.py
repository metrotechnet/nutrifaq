import json
import logging
import os
import sys
from pathlib import Path

from docx import Document

logger = logging.getLogger(__name__)

# Resolve repo and nutrifaq-dbase roots from api/db_pipeline/
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KB_ROOT = REPO_ROOT / "nutrifaq-dbase"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.services.logging import configure_logging  # noqa: E402
from api.services.database_regeneration_service import _write_progress_snapshot  # noqa: E402

configure_logging()


SUPPORTED_SUFFIXES = (".docx", ".md", ".markdown")


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
        logger.exception("Failed to load pipeline state from %s", state_path)
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_pipeline_state(kb_root: Path, payload: dict) -> None:
    state_path = _pipeline_state_path(kb_root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _filter_new_files(kb_root: Path, candidates: list[Path], step_name: str) -> list[Path]:
    if not _new_file_only_enabled():
        return candidates

    state = _load_pipeline_state(kb_root)
    processed = state.get(step_name, {})
    if not isinstance(processed, dict):
        return candidates

    filtered = []
    for file_path in candidates:
        relative_name = file_path.name
        previous_mtime = processed.get(relative_name)
        current_mtime = file_path.stat().st_mtime_ns if file_path.exists() else None
        if previous_mtime is None or current_mtime is None or current_mtime > previous_mtime:
            filtered.append(file_path)
    return filtered


def resolve_kb_root() -> Path:
    """Resolve knowledge-base root from CLI arg, env, or default path."""
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        return Path(sys.argv[1]).resolve()

    kb_root_env = os.getenv("NUTRIFAQ_KB_ROOT", "").strip()
    if kb_root_env:
        return Path(kb_root_env).resolve()

    return DEFAULT_KB_ROOT


def extract_text_from_docx(docx_path):
    """Extract text from a Word document."""
    doc = Document(docx_path)
    full_text = []
    for para in doc.paragraphs:
        if para.text.strip():
            full_text.append(para.text)
    return "\n".join(full_text)


def extract_text_from_markdown(markdown_path):
    """Read a Markdown file as UTF-8 text."""
    try:
        return markdown_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.exception("UTF-8 decode failed for %s; retrying with latin-1", markdown_path)
        try:
            return markdown_path.read_text(encoding="latin-1")
        except Exception:
            logger.exception("Failed to read markdown file %s using fallback encoding", markdown_path)
            raise


def extract_all_documents(folder_path, output_folder=None):
    """Extract text from all supported document files and save as .txt."""
    logger.info("Extracting documents from: %s", folder_path)
    folder_path = Path(folder_path)

    if output_folder is None:
        output_folder = str(folder_path.parent / "transcripts")
    os.makedirs(output_folder, exist_ok=True)

    output_dir = Path(output_folder)
    if not _new_file_only_enabled():
        for existing_file in output_dir.iterdir():
            if existing_file.is_file():
                existing_file.unlink(missing_ok=True)

    supported_files = []
    for filename in os.listdir(folder_path):
        if filename.startswith("~$"):
            continue
        lower_name = filename.lower()
        if lower_name.endswith(SUPPORTED_SUFFIXES):
            supported_files.append(Path(folder_path) / filename)

    supported_files = _filter_new_files(folder_path, supported_files, "extract_docx") if _new_file_only_enabled() else supported_files
    total_files = len(supported_files)
    _write_progress_snapshot("extract_docx", 0, total_files, "files")

    logger.info("Found %s documents", len(supported_files))

    processed_files = 0
    processed_map = _load_pipeline_state(folder_path)
    for file_path in supported_files:
        filename = file_path.name

        try:
            if file_path.suffix.lower() == ".docx":
                text = extract_text_from_docx(file_path)
            else:
                text = extract_text_from_markdown(file_path)

            if not text.strip():
                continue

            txt_filename = file_path.stem + ".txt"
            txt_path = output_dir / txt_filename
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)

            logger.info("  Saved to %s (%s characters)", txt_filename, len(text))

        except Exception as e:
            logger.exception("  Error processing %s: %s", filename, e)
        finally:
            processed_files += 1
            processed_map.setdefault("extract_docx", {})[filename] = file_path.stat().st_mtime_ns
            _write_progress_snapshot("extract_docx", processed_files, total_files, "files")

    if _new_file_only_enabled():
        _save_pipeline_state(folder_path, processed_map)

if __name__ == "__main__":
    kb_root = resolve_kb_root()
    transcript_folder = str(kb_root / "documents")

    if not os.path.exists(transcript_folder):
        logger.error("Error: Folder '%s' not found", transcript_folder)
    else:
        logger.info("Starting extraction from: %s", transcript_folder)
        extract_all_documents(transcript_folder)
        logger.info("Extraction complete!")

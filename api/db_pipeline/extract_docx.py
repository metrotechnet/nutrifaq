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
        return markdown_path.read_text(encoding="latin-1")


def extract_all_documents(folder_path, output_folder=None):
    """Extract text from all supported document files and save as .txt."""
    logger.info("Extracting documents from: %s", folder_path)
    
    if output_folder is None:
        output_folder = str(Path(folder_path).parent / "transcripts")
    os.makedirs(output_folder, exist_ok=True)

    output_dir = Path(output_folder)
    for existing_file in output_dir.iterdir():
        if existing_file.is_file():
            existing_file.unlink(missing_ok=True)

    supported_files = []
    for filename in os.listdir(folder_path):
        if filename.startswith("~$"):
            continue
        lower_name = filename.lower()
        if lower_name.endswith(SUPPORTED_SUFFIXES):
            supported_files.append(filename)

    total_files = len(supported_files)
    _write_progress_snapshot("extract_docx", 0, total_files, "files")

    logger.info("Found %s documents", len(supported_files))

    processed_files = 0
    for filename in supported_files:
        file_path = Path(folder_path) / filename

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
            _write_progress_snapshot("extract_docx", processed_files, total_files, "files")
            

if __name__ == "__main__":
    kb_root = resolve_kb_root()
    transcript_folder = str(kb_root / "documents")

    if not os.path.exists(transcript_folder):
        logger.error("Error: Folder '%s' not found", transcript_folder)
    else:
        logger.info("Starting extraction from: %s", transcript_folder)
        extract_all_documents(transcript_folder)
        logger.info("Extraction complete!")

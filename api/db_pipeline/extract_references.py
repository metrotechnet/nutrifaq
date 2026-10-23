"""
Extract references from Nutrifaq documents.

Reads all supported document files in nutrifaq-dbase/documents and extracts:
- Inline PMID references (PMID: 12345678)
- Numbered reference sections (References)
- Markdown metadata and cleaned text for .md files

Outputs JSON file: nutrifaq-dbase/references.json
"""

import json
import logging
import os
import re
import sys
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

import docx

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]

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
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_pipeline_state(kb_root: Path, payload: dict) -> None:
    state_path = _pipeline_state_path(kb_root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _filter_new_files(kb_root: Path, candidates: list[Path]) -> list[Path]:
    if not _new_file_only_enabled():
        return candidates
    state = _load_pipeline_state(kb_root)
    processed = state.get("extract_docx", {})
    if not isinstance(processed, dict):
        return candidates
    allowed = set(processed.keys())
    return [file_path for file_path in candidates if file_path.name in allowed]


# Purpose: Implement a focused unit of backend behavior used by routes or services.
# Inputs/Outputs: See signature and return annotation for contract details.
def resolve_kb_path() -> Path:
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        return Path(sys.argv[1]).resolve()

    kb_root_env = os.getenv("NUTRIFAQ_KB_ROOT", "").strip()
    if kb_root_env:
        return Path(kb_root_env).resolve()

    return SCRIPT_DIR.parents[1] / "nutrifaq-dbase"


def read_docx(path):
    """Read a .docx file and return full text."""
    doc = docx.Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def read_markdown(path):
    """Read a Markdown file and return full text."""
    return Path(path).read_text(encoding="utf-8", errors="replace")


def extract_pmids(text):
    """Extract all PMID numbers from text."""
    matches = re.findall(r"PMID:\s*(\d+)", text)
    seen = set()
    unique = []
    for pmid in matches:
        if pmid not in seen:
            seen.add(pmid)
            unique.append(pmid)
    return unique


def parse_markdown_metadata(text):
    """Extract frontmatter or leading heading metadata from Markdown."""
    metadata = {}

    front_matter = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if front_matter:
        section = front_matter.group(1)
        for line in section.splitlines():
            if not line.strip() or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().lower().replace("-", "_")
            value = value.strip().strip('"\'')
            if key and value:
                metadata[key] = value
        text = text[front_matter.end():]

    title_match = re.search(r"^\s*#\s+(.+?)\s*$", text, re.MULTILINE)
    if title_match and "title" not in metadata:
        metadata["title"] = title_match.group(1).strip()

    return metadata, text


def extract_markdown_references(text):
    """Extract a markdown References section as numbered citation entries."""
    ref_section_match = re.search(r"(?im)^(?:#+\s*)?(?:references?|r[eé]f[eé]rences?)\s*:??\s*$", text)
    if not ref_section_match:
        return []

    section_start = ref_section_match.end()
    section_text = text[section_start:]
    lines = section_text.splitlines()

    entries = []
    current_lines = []

    for line in lines:
        if re.match(r"^\s*#+\s+", line):
            break

        if not line.strip():
            if current_lines:
                entries.append(" ".join(current_lines).strip())
                current_lines = []
            continue

        if re.match(r"^\s*(?:\d+\.?\)|\d+\.|[-*])\s+", line):
            if current_lines:
                entries.append(" ".join(current_lines).strip())
            current_lines = [re.sub(r"^\s*(?:\d+\.?\)|\d+\.|[-*])\s*", "", line).strip()]
        else:
            if current_lines:
                current_lines.append(line.strip())
            elif line.strip():
                current_lines = [line.strip()]

    if current_lines:
        entries.append(" ".join(current_lines).strip())

    references = []
    for index, citation in enumerate([entry for entry in entries if entry], start=1):
        references.append({"number": index, "citation": citation})

    return references


def cleanup_markdown_text(text):
    """Remove markdown links and clean remaining markdown formatting from extracted body text."""
    cleaned = text or ""
    cleaned = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", cleaned)
    cleaned = re.sub(r"<https?://[^>\s]+>", "", cleaned)
    cleaned = re.sub(r"https?://[^\s)]+", "", cleaned)
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*(.*?)\*", r"\1", cleaned)
    cleaned = re.sub(r"__(.*?)__", r"\1", cleaned)
    cleaned = re.sub(r"_(.*?)_", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"^\s*#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*[-*]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\r\n?", "\n", cleaned)
    return cleaned.strip()


def _normalize_reference_title(value):
    """Normalize headings like 'Références' to compare them reliably."""
    normalized = unicodedata.normalize("NFKD", value.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.strip().rstrip(":")
    return re.sub(r"\s+", " ", normalized)


def extract_bibliography(text):
    """Extract a bibliography list from a References/Références section."""
    if not text:
        return []

    lines = text.splitlines()
    start_index = None
    for index, line in enumerate(lines):
        cleaned = line.strip()
        if not cleaned:
            continue
        heading = re.sub(r"^#+\s*", "", cleaned)
        heading = heading.rstrip(":").strip()
        if _normalize_reference_title(heading) in {"reference", "references"}:
            start_index = index + 1
            break

    if start_index is None:
        return []

    entries = []
    current_number = None
    current_citation = []

    def flush_current_entry():
        nonlocal current_number, current_citation
        if current_number is not None and current_citation:
            citation = " ".join(current_citation).strip()
            if citation:
                entries.append({"number": current_number, "citation": citation})
        current_number = None
        current_citation = []

    for line in lines[start_index:]:
        stripped = line.strip()
        if not stripped:
            continue

        if re.match(r"^#+\s+", line):
            flush_current_entry()
            break

        bullet_match = re.match(r"^(?:[-*])\s+(.*)$", stripped)
        if bullet_match:
            if current_number is not None and current_citation:
                flush_current_entry()
            current_number = len(entries) + 1
            current_citation = [bullet_match.group(1).strip()]
            continue

        numbered_match = re.match(r"^(?:\(?)(\d+)(?:\)|\.)\s+(.*)$", stripped)
        if numbered_match:
            flush_current_entry()
            current_number = int(numbered_match.group(1))
            current_citation = [numbered_match.group(2).strip()]
            continue

        if current_number is not None:
            current_citation.append(stripped)
        elif stripped and stripped[0].isupper():
            current_number = len(entries) + 1
            current_citation = [stripped]

    flush_current_entry()
    return entries


def extract_markdown_document(file_path: Path):
    """Process a Markdown document and return text, metadata, and references."""
    raw_text = read_markdown(file_path)
    metadata, remaining_text = parse_markdown_metadata(raw_text)
    cleaned_text = cleanup_markdown_text(remaining_text)
    pmids = extract_pmids(cleaned_text)
    markdown_references = extract_markdown_references(remaining_text)
    bibliography = extract_bibliography(cleaned_text)

    if markdown_references:
        bibliography = []
    elif not bibliography:
        bibliography = []

    return {
        "filename": file_path.name,
        "metadata": metadata,
        "text": cleaned_text,
        "references": {
            "pmids": pmids,
            "bibliography": bibliography,
            "markdown_references": markdown_references,
        },
    }


def process_documents(documents_dir: Path):
    """Process supported document files and extract references."""
    if not documents_dir.exists():
        logger.error("Documents directory not found: %s", documents_dir)
        return []

    files = sorted(
        f for f in documents_dir.iterdir()
        if f.suffix.lower() in SUPPORTED_SUFFIXES and not f.name.startswith("~$")
    )
    if _new_file_only_enabled():
        files = _filter_new_files(documents_dir.parent, files)
    total_files = len(files)
    _write_progress_snapshot("extract_references", 0, total_files, "files")

    logger.info("Found %s supported files in %s", len(files), documents_dir)

    if total_files == 0:
        _write_progress_snapshot("extract_references", 1, 1, "files")
        return results if 'results' in locals() else []

    results = []
    processed_files = 0
    processed_map = _load_pipeline_state(documents_dir.parent)
    for fpath in files:
        try:
            if fpath.suffix.lower() == ".docx":
                text = read_docx(str(fpath))
                pmids = extract_pmids(text)
                bibliography = extract_bibliography(text)
                doc_entry = {
                    "filename": fpath.name,
                    "metadata": {},
                    "text": text,
                    "references": {
                        "pmids": pmids,
                        "bibliography": bibliography,
                    },
                }
            else:
                doc_entry = extract_markdown_document(fpath)
                if doc_entry.get("references", {}).get("markdown_references"):
                    doc_entry["references"]["bibliography"] = []

            results.append(doc_entry)

            ref_count = len(doc_entry.get("references", {}).get("pmids", [])) + len(doc_entry.get("references", {}).get("bibliography", [])) + len(doc_entry.get("references", {}).get("markdown_references", []))
            if ref_count > 0:
                parts = []
                if doc_entry.get("references", {}).get("pmids"):
                    parts.append(f"{len(doc_entry['references']['pmids'])} PMIDs")
                if doc_entry.get("references", {}).get("bibliography"):
                    parts.append(f"{len(doc_entry['references']['bibliography'])} bibliography entries")
                if doc_entry.get("references", {}).get("markdown_references"):
                    parts.append(f"{len(doc_entry['references']['markdown_references'])} markdown references")
                logger.info("%s: %s", fpath.name, ', '.join(parts))
            else:
                logger.info("%s: no references found", fpath.name)

        except Exception as e:
            logger.exception("Failed to read %s: %s", fpath.name, e)
        finally:
            processed_files += 1
            processed_map.setdefault("extract_references", {})[fpath.name] = fpath.stat().st_mtime_ns
            _write_progress_snapshot("extract_references", processed_files, total_files, "files")

    if _new_file_only_enabled():
        _save_pipeline_state(documents_dir.parent, processed_map)

    return results


# Purpose: Implement a focused unit of backend behavior used by routes or services.
# Inputs/Outputs: See signature and return annotation for contract details.
def main() -> None:
    kb_root = resolve_kb_path()
    documents_dir = kb_root / "documents"
    output_path = kb_root / "references.json"

    logger.info("Scanning documents in: %s", documents_dir)
    results = process_documents(documents_dir)

    payload = {
        "total_documents": len(results),
        "documents": results,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    logger.info("Saved references to: %s", output_path)


if __name__ == "__main__":
    main()


"""
Extract references from Nutrifaq documents.

Reads all .docx files in nutrifaq-dbase/documents and extracts:
- Inline PMID references (PMID: 12345678)
- Numbered reference sections (References)

Outputs JSON file: nutrifaq-dbase/references.json
"""

import json
import os
import re
import sys
from pathlib import Path

import docx

SCRIPT_DIR = Path(__file__).resolve().parent


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


def extract_bibliography(text):
    """Extract numbered reference list from a References section."""
    match = re.search(r"(?im)^r[eé]f[eé]rences?\s*$", text)
    if not match:
        return []

    ref_text = text[match.end():]
    entries = []
    lines = ref_text.split("\n")
    current_number = None
    current_citation = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        num_match = re.match(r"^(\d+)[\.\)]\s+(.*)", line)
        if num_match:
            if current_number is not None and current_citation:
                entries.append(
                    {
                        "number": current_number,
                        "citation": " ".join(current_citation).strip(),
                    }
                )
            current_number = int(num_match.group(1))
            current_citation = [num_match.group(2)]
        elif current_number is not None:
            current_citation.append(line)

    if current_number is not None and current_citation:
        entries.append(
            {
                "number": current_number,
                "citation": " ".join(current_citation).strip(),
            }
        )

    return entries


def process_documents(documents_dir: Path):
    """Process all .docx files and extract references."""
    if not documents_dir.exists():
        print(f"Documents directory not found: {documents_dir}")
        return []

    results = []
    files = sorted(
        f for f in documents_dir.iterdir() if f.suffix.lower() == ".docx" and not f.name.startswith("~$")
    )

    print(f"Found {len(files)} .docx files in {documents_dir}\n")

    for fpath in files:
        try:
            text = read_docx(str(fpath))
            pmids = extract_pmids(text)
            bibliography = extract_bibliography(text)

            doc_entry = {
                "filename": fpath.name,
                "text": text,
                "references": {
                    "pmids": pmids,
                    "bibliography": bibliography,
                },
            }
            results.append(doc_entry)

            ref_count = len(pmids) + len(bibliography)
            if ref_count > 0:
                parts = []
                if pmids:
                    parts.append(f"{len(pmids)} PMIDs")
                if bibliography:
                    parts.append(f"{len(bibliography)} bibliography entries")
                print(f"{fpath.name}: {', '.join(parts)}")
            else:
                print(f"{fpath.name}: no references found")

        except Exception as e:
            print(f"Failed to read {fpath.name}: {e}")

    return results


def main() -> None:
    kb_root = resolve_kb_path()
    documents_dir = kb_root / "documents"
    output_path = kb_root / "references.json"

    print(f"Scanning documents in: {documents_dir}")
    results = process_documents(documents_dir)

    payload = {
        "total_documents": len(results),
        "documents": results,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    print(f"\nSaved references to: {output_path}")


if __name__ == "__main__":
    main()


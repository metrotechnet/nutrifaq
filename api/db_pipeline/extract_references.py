"""
Extract references from Nutrifaq documents.

Reads all .docx files in nutrifaq-dbase/documents and extracts:
- Inline PMID references (PMID: 12345678)
- Numbered reference sections (References)

Outputs JSON file: nutrifaq-dbase/references.json
"""

import json
import re
from pathlib import Path

import docx

SCRIPT_DIR = Path(__file__).resolve().parent
KB_PATH = SCRIPT_DIR.parents[1] / "nutrifaq-dbase"
DOCUMENTS_DIR = KB_PATH / "documents"
OUTPUT_FILE = KB_PATH / "references.json"


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


def process_documents():
    """Process all .docx files and extract references."""
    if not DOCUMENTS_DIR.exists():
        print(f"Documents directory not found: {DOCUMENTS_DIR}")
        return []

    results = []
    files = sorted(
        f for f in DOCUMENTS_DIR.iterdir() if f.suffix.lower() == ".docx" and not f.name.startswith("~$")
    )

    print(f"Found {len(files)} .docx files in {DOCUMENTS_DIR}\n")

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


def main():
    documents = process_documents()

    output = []
    for doc in documents:
        output.append(
            {
                "filename": doc["filename"],
                "text": doc["text"],
                "references": doc["references"],
            }
        )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Done. Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

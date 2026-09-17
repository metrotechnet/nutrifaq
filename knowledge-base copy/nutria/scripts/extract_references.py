"""
Extract References from Nutria Documents
=========================================
Reads all .docx files in nutria/documents, extracts:
  - Inline PMID references (PMID: 12345678)
  - Numbered reference sections (Références / References)

Outputs a JSON file: nutria/references.json
Format:
{
  "documents": [
    {
      "filename": "Capsule 061025.docx",
      "text": "full document text...",
      "references": {
        "pmids": ["27050205", "31139631", ...],
        "bibliography": [
          {"number": 1, "citation": "Author, Title. Journal, 2020..."},
          ...
        ]
      }
    },
    ...
  ]
}

Usage:
    python extract_references.py
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime

import docx

SCRIPT_DIR = Path(__file__).parent
KB_PATH = SCRIPT_DIR.parent
DOCUMENTS_DIR = KB_PATH / "documents_copy"
OUTPUT_FILE = KB_PATH / "references.json"


def read_docx(path):
    """Read a .docx file and return full text."""
    doc = docx.Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def extract_pmids(text):
    """Extract all PMID numbers from text (handles regular and non-breaking spaces)."""
    # Match PMID: followed by any whitespace (including \xa0) then digits
    matches = re.findall(r'PMID:\s*(\d+)', text)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for pmid in matches:
        if pmid not in seen:
            seen.add(pmid)
            unique.append(pmid)
    return unique


def extract_bibliography(text):
    """Extract numbered reference list from a Références/References section."""
    # Find the reference section header
    match = re.search(r'(?im)^r[eé]f[eé]rences?\s*$', text)
    if not match:
        return []

    ref_text = text[match.end():]

    # Match numbered entries: "1." or "1)" at start of line
    entries = []
    # Split into lines and accumulate multi-line entries
    lines = ref_text.split('\n')
    current_number = None
    current_citation = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if this is a new numbered entry
        num_match = re.match(r'^(\d+)[\.\)]\s+(.*)', line)
        if num_match:
            # Save previous entry
            if current_number is not None and current_citation:
                entries.append({
                    "number": current_number,
                    "citation": " ".join(current_citation).strip(),
                })
            current_number = int(num_match.group(1))
            current_citation = [num_match.group(2)]
        elif current_number is not None:
            # Continuation of previous entry
            current_citation.append(line)

    # Save last entry
    if current_number is not None and current_citation:
        entries.append({
            "number": current_number,
            "citation": " ".join(current_citation).strip(),
        })

    return entries


def process_documents():
    """Process all .docx files and extract references."""
    if not DOCUMENTS_DIR.exists():
        print(f"⚠️  Documents directory not found: {DOCUMENTS_DIR}")
        return []

    results = []
    files = sorted(f for f in DOCUMENTS_DIR.iterdir()
                   if f.suffix.lower() == '.docx' and not f.name.startswith('~$'))

    print(f"📁 Found {len(files)} .docx files in {DOCUMENTS_DIR}\n")

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
                print(f"📄 {fpath.name}: {', '.join(parts)}")
            else:
                print(f"📄 {fpath.name}: no references found")

        except Exception as e:
            print(f"⚠️  Failed to read {fpath.name}: {e}")

    return results


def main():
    print("=" * 60)
    print("🔍 Extracting references from Nutria documents")
    print("=" * 60 + "\n")

    documents = process_documents()

    # Summary
    total_pmids = sum(len(d["references"]["pmids"]) for d in documents)
    total_bib = sum(len(d["references"]["bibliography"]) for d in documents)
    docs_with_refs = sum(1 for d in documents
                         if d["references"]["pmids"] or d["references"]["bibliography"])

    output = []
    for doc in documents:
        output.append({
            "filename": doc["filename"],
            "text": doc["text"],
            "references": doc["references"],
        })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"✅ Done!")
    print(f"   Documents processed: {len(documents)}")
    print(f"   Documents with references: {docs_with_refs}")
    print(f"   Total unique PMIDs: {total_pmids}")
    print(f"   Total bibliography entries: {total_bib}")
    print(f"   Output: {OUTPUT_FILE}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

"""
Generate transcripts_chromadb.json from transcripts and documents.

Usage:
    python generate_transcripts_json.py <path_to_knowledge_base>
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.services.database_regeneration_service import _write_progress_snapshot  # noqa: E402



def generate_transcripts_json(kb_dir: Path):
    """Create transcripts_chromadb.json file from transcripts and JSON documents."""
    print("Generating transcripts_chromadb.json...")

    transcripts_dir = kb_dir / "transcripts"
    documents_dir = kb_dir / "documents"
    output_path = kb_dir / "transcripts_chromadb.json"

    # Keep existing transcripts; this step consumes .txt files from transcripts/.
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    # Start from a clean output file for each regeneration run.
    if output_path.exists():
        output_path.unlink()

    documents = []
    doc_counter = 0
    transcript_files = list(transcripts_dir.glob("*.txt")) if transcripts_dir.exists() else []
    json_files = list(documents_dir.glob("*.json")) if documents_dir.exists() else []
    total_files = len(transcript_files) + len(json_files)
    processed_files = 0
    _write_progress_snapshot("generate_transcripts_json", 0, total_files, "files")

    if transcript_files:
        print(f"Processing {len(transcript_files)} transcript files...")

        for file_path in tqdm(transcript_files, desc="Processing transcripts"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()

                if not text.strip():
                    continue

                doc_id = f"doc_{doc_counter:04d}_{file_path.stem}"
                doc_counter += 1

                metadata = {
                    "source": file_path.name,
                    "reference": file_path.stem,
                    "type": "transcript",
                }

                date_match = re.search(r"(\d{2})(\d{2})(\d{2})", file_path.stem)
                if date_match:
                    day, month, year = date_match.groups()
                    metadata["date"] = f"20{year}-{month}-{day}"

                documents.append({"id": doc_id, "text": text, "metadata": metadata})

            except Exception as e:
                print(f"Error processing {file_path.name}: {e}")
                continue
            finally:
                processed_files += 1
                _write_progress_snapshot("generate_transcripts_json", processed_files, total_files, "files")

    if json_files:
        print(f"Processing {len(json_files)} JSON files...")

        for json_file in tqdm(json_files, desc="Processing JSON files"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    json_data = json.load(f)

                if isinstance(json_data, list):
                    entries = json_data
                elif isinstance(json_data, dict):
                    entries = [json_data]
                else:
                    print(f"Unsupported JSON structure in {json_file.name}")
                    continue

                for entry in entries:
                    if not isinstance(entry, dict):
                        continue

                    text_parts = []
                    entry_id = entry.get("id", f"entry_{doc_counter}")

                    if "titre" in entry or "title" in entry:
                        title = entry.get("titre") or entry.get("title")
                        text_parts.append(f"Titre: {title}")

                    if "label" in entry:
                        text_parts.append(f"Label: {entry['label']}")

                    if "auteur" in entry or "author" in entry:
                        author = entry.get("auteur") or entry.get("author")
                        text_parts.append(f"Auteur: {author}")

                    if "resume" in entry or "summary" in entry:
                        resume = entry.get("resume") or entry.get("summary")
                        if resume:
                            text_parts.append(f"\nResume: {resume}")

                    if "description" in entry:
                        text_parts.append(f"\nDescription: {entry['description']}")

                    if "categorie" in entry or "category" in entry:
                        cat = entry.get("categorie") or entry.get("category")
                        text_parts.append(f"\nCategorie: {cat}")

                    for key in ["editeur", "publisher", "parution", "pages", "langue", "language"]:
                        if key in entry and entry[key]:
                            text_parts.append(f"{key.capitalize()}: {entry[key]}")

                    text = "\n".join(text_parts)

                    if not text.strip():
                        text = "\n".join(
                            [f"{k}: {v}" for k, v in entry.items() if v and k != "classification"]
                        )

                    doc_id = f"doc_{doc_counter:04d}_{entry_id}"
                    doc_counter += 1

                    metadata = {
                        "source": json_file.name,
                        "type": entry.get("type", "json_entry"),
                        "entry_id": entry_id,
                    }

                    for key in ["categorie", "category", "editeur", "publisher", "langue", "language"]:
                        if key in entry and entry[key]:
                            metadata[key] = entry[key]

                    documents.append({"id": doc_id, "text": text, "metadata": metadata})

            except Exception as e:
                print(f"Error processing {json_file.name}: {e}")
                continue
            finally:
                processed_files += 1
                _write_progress_snapshot("generate_transcripts_json", processed_files, total_files, "files")

    if not documents:
        print("No documents to process")
        print("Please add .txt files to nutrifaq-dbase/transcripts/")
        print("or .json files to nutrifaq-dbase/documents/")
        return False

    transcripts_data = {
        "knowledge_base": "agent",
        "format": "chromadb",
        "total_documents": len(documents),
        "extracted_at": datetime.now().isoformat(),
        "documents": documents,
    }

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(transcripts_data, f, ensure_ascii=False, indent=2)

        print(f"Created transcripts_chromadb.json with {len(documents)} documents")
        print(f"Saved to: {output_path}")
        return True
    except Exception as e:
        print(f"Error saving transcripts_chromadb.json: {e}")
        return False


# Purpose: Implement a focused unit of backend behavior used by routes or services.
# Inputs/Outputs: See signature and return annotation for contract details.
def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python generate_transcripts_json.py <path_to_knowledge_base>")
        return 1

    kb_dir = Path(sys.argv[1])

    if not kb_dir.exists():
        print(f"Directory not found: {kb_dir}")
        return 1

    success = generate_transcripts_json(kb_dir)
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = main()
    # Avoid debugger interruptions on expected non-zero exits.
    if sys.gettrace() is None and exit_code != 0:
        raise SystemExit(exit_code)

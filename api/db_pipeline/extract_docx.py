import os
import sys
from pathlib import Path

from docx import Document

# Resolve repo and nutrifaq-dbase roots from api/db_pipeline/
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KB_ROOT = REPO_ROOT / "nutrifaq-dbase"


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


def extract_all_documents(folder_path, output_folder=None):
    """Extract text from all .docx files and save as .txt."""
    if output_folder is None:
        output_folder = str(Path(folder_path).parent / "transcripts")
    os.makedirs(output_folder, exist_ok=True)

    docx_files = [f for f in os.listdir(folder_path) if f.endswith(".docx") and not f.startswith("~$")]

    print(f"Found {len(docx_files)} documents\n")

    for filename in docx_files:
        file_path = os.path.join(folder_path, filename)
        print(f"Processing: {filename}")

        try:
            text = extract_text_from_docx(file_path)

            if not text.strip():
                print("  No text found")
                continue

            txt_filename = os.path.splitext(filename)[0] + ".txt"
            txt_path = os.path.join(output_folder, txt_filename)

            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)

            print(f"  Saved to {txt_filename} ({len(text)} characters)")

        except Exception as e:
            print(f"  Error: {str(e)}")


if __name__ == "__main__":
    kb_root = resolve_kb_root()
    transcript_folder = str(kb_root / "documents")

    if not os.path.exists(transcript_folder):
        print(f"Error: Folder '{transcript_folder}' not found")
    else:
        print(f"Extracting documents from: {transcript_folder}\n")
        extract_all_documents(transcript_folder)
        print("\nExtraction complete! Check the 'transcripts' folder")

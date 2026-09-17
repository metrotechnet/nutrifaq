"""
Generate transcripts_chromadb.json from transcripts and documents

This script reads all .txt files from knowledge-base/agent/transcripts/
and .json files from knowledge-base/agent/documents/ and creates a single
transcripts_chromadb.json file that can be indexed to ChromaDB.

Usage:
    python generate_transcripts_json.py <path_to_knowledge_base_agent>
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime
from tqdm import tqdm


def generate_transcripts_json(agent_dir: Path):
    """Create transcripts_chromadb.json file from transcripts and JSON documents"""
    print(f"📝 Generating transcripts_chromadb.json...")
    
    transcripts_dir = agent_dir / "transcripts"
    documents_dir = agent_dir / "documents"
    output_path = agent_dir / "transcripts_chromadb.json"
    
    # Get agent ID from config.json
    config_path = agent_dir / "config.json"
    agent_id = "agent"
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                agent_id = config.get("agent_id", "agent")
        except Exception as e:
            print(f"⚠️  Could not read agent_id from config.json: {e}")
    
    documents = []
    doc_counter = 0
    
    # Process transcript files (.txt)
    if transcripts_dir.exists():
        transcript_files = list(transcripts_dir.glob("*.txt"))
        if transcript_files:
            print(f"📄 Processing {len(transcript_files)} transcript files...")
            
            for file_path in tqdm(transcript_files, desc="Processing transcripts"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        text = f.read()
                    
                    if not text.strip():
                        continue
                    
                    # Create document ID and metadata
                    doc_id = f"doc_{doc_counter:04d}_{file_path.stem}"
                    doc_counter += 1
                    
                    # Basic metadata
                    metadata = {
                        "source": file_path.name,
                        "reference": file_path.stem,
                        "type": "transcript"
                    }
                    
                    # Try to extract date from filename if present (DDMMYY format)
                    date_match = re.search(r'(\d{2})(\d{2})(\d{2})', file_path.stem)
                    if date_match:
                        day, month, year = date_match.groups()
                        metadata["date"] = f"20{year}-{month}-{day}"
                    
                    # Add to documents array
                    documents.append({
                        "id": doc_id,
                        "text": text,
                        "metadata": metadata
                    })
                    
                except Exception as e:
                    print(f"⚠️  Error processing {file_path.name}: {e}")
                    continue
    
    # Process JSON files (each entry becomes a separate document)
    if documents_dir.exists():
        json_files = list(documents_dir.glob("*.json"))
        if json_files:
            print(f"📚 Processing {len(json_files)} JSON files...")
            
            for json_file in tqdm(json_files, desc="Processing JSON files"):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                    
                    # Handle both array and single object
                    if isinstance(json_data, list):
                        entries = json_data
                    elif isinstance(json_data, dict):
                        entries = [json_data]
                    else:
                        print(f"⚠️  Unsupported JSON structure in {json_file.name}")
                        continue
                    
                    # Create a document for each entry
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                        
                        # Generate readable text from the entry
                        text_parts = []
                        
                        # Use entry's own ID if available, otherwise generate one
                        entry_id = entry.get("id", f"entry_{doc_counter}")
                        
                        # Build readable text from key fields
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
                                text_parts.append(f"\nRésumé: {resume}")
                        
                        if "description" in entry:
                            text_parts.append(f"\nDescription: {entry['description']}")
                        
                        if "categorie" in entry or "category" in entry:
                            cat = entry.get("categorie") or entry.get("category")
                            text_parts.append(f"\nCatégorie: {cat}")
                        
                        # Add any other important fields
                        for key in ["editeur", "publisher", "parution", "pages", "langue", "language"]:
                            if key in entry and entry[key]:
                                text_parts.append(f"{key.capitalize()}: {entry[key]}")
                        
                        # Combine all parts
                        text = "\n".join(text_parts)
                        
                        if not text.strip():
                            # Fallback: convert entire entry to text
                            text = "\n".join([f"{k}: {v}" for k, v in entry.items() if v and k != "classification"])
                        
                        # Create document ID
                        doc_id = f"doc_{doc_counter:04d}_{entry_id}"
                        doc_counter += 1
                        
                        # Build metadata from entry fields
                        metadata = {
                            "source": json_file.name,
                            "type": entry.get("type", "json_entry"),
                            "entry_id": entry_id
                        }
                        
                        # Add relevant fields to metadata
                        for key in ["categorie", "category", "editeur", "publisher", "langue", "language"]:
                            if key in entry and entry[key]:
                                metadata[key] = entry[key]
                        
                        # Add to documents array
                        documents.append({
                            "id": doc_id,
                            "text": text,
                            "metadata": metadata
                        })
                    
                except Exception as e:
                    print(f"⚠️  Error processing {json_file.name}: {e}")
                    continue
    
    if not documents:
        print("⚠️  No documents to process")
        print("   Please add .txt files to knowledge-base/agent/transcripts/")
        print("   or .json files to knowledge-base/agent/documents/")
        return False
    
    # Create the complete structure
    transcripts_data = {
        "knowledge_base": agent_id,
        "format": "chromadb",
        "total_documents": len(documents),
        "extracted_at": datetime.now().isoformat(),
        "documents": documents
    }
    
    # Save to file
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(transcripts_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Created transcripts_chromadb.json with {len(documents)} documents")
        print(f"   Saved to: {output_path}")
        return True
    except Exception as e:
        print(f"❌ Error saving transcripts_chromadb.json: {e}")
        return False


def main():
    if len(sys.argv) != 2:
        print("Usage: python generate_transcripts_json.py <path_to_knowledge_base_agent>")
        sys.exit(1)
    
    agent_dir = Path(sys.argv[1])
    
    if not agent_dir.exists():
        print(f"❌ Directory not found: {agent_dir}")
        sys.exit(1)
    
    success = generate_transcripts_json(agent_dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

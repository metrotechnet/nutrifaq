import os
from docx import Document
from pathlib import Path

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent

def extract_text_from_docx(docx_path):
    """Extract text from a Word document"""
    doc = Document(docx_path)
    full_text = []
    for para in doc.paragraphs:
        if para.text.strip():
            full_text.append(para.text)
    return '\n'.join(full_text)

def extract_all_documents(folder_path, output_folder=str(PROJECT_ROOT / "transcripts")):
    """Extract text from all .docx files and save as .txt"""
    os.makedirs(output_folder, exist_ok=True)
    
    docx_files = [f for f in os.listdir(folder_path) if f.endswith('.docx') and not f.startswith('~$')]
    
    print(f"Found {len(docx_files)} documents\n")
    
    for filename in docx_files:
        file_path = os.path.join(folder_path, filename)
        print(f"Processing: {filename}")
        
        try:
            text = extract_text_from_docx(file_path)
            
            if not text.strip():
                print(f"  ⚠️ No text found")
                continue
            
            # Save as txt file
            txt_filename = os.path.splitext(filename)[0] + ".txt"
            txt_path = os.path.join(output_folder, txt_filename)
            
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(text)
            
            print(f"  ✅ Saved to {txt_filename} ({len(text)} characters)")
            
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")

if __name__ == "__main__":
    transcript_folder = r"documents"
    
    if not os.path.exists(transcript_folder):
        print(f"Error: Folder '{transcript_folder}' not found")
    else:
        print(f"Extracting documents from: {transcript_folder}\n")
        extract_all_documents(transcript_folder)
        print("\n✅ Extraction complete! Check the 'transcripts' folder")

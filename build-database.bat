@echo off
REM ============================================
REM Build Database - Index Documents to ChromaDB
REM ============================================
REM This script indexes your documents to ChromaDB
REM for RAG (Retrieval-Augmented Generation)
REM ============================================

echo.
echo ========================================
echo   Building ChromaDB Vector Database
echo ========================================
echo.

REM Check if knowledge-base/agent exists
if not exist "knowledge-base\agent" (
    echo [ERROR] knowledge-base\agent folder not found!
    echo Please ensure you have run the agent creation script first.
    echo.
    pause
    exit /b 1
)

REM Check if transcripts folder has files
if not exist "knowledge-base\agent\transcripts\*.*" (
    if not exist "knowledge-base\agent\documents\*.*" (
        echo [ERROR] No documents found in knowledge-base\agent\transcripts or documents
        echo Please add your documents first.
        echo.
        pause
        exit /b 1
    )
)

echo [INFO] Generating transcripts_chromadb.json from source documents...
echo.

REM Generate transcripts_chromadb.json from transcripts and documents
python.exe .\core\generate_transcripts_json.py .\knowledge-base\agent\

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed to generate transcripts_chromadb.json!
    echo Check that:
    echo   1. You have added documents to knowledge-base\agent\transcripts\ or documents\
    echo   2. Python is installed and in PATH
    echo.
    pause
    exit /b 1
)

echo.
echo [INFO] Indexing documents to ChromaDB...
echo.

REM Run the indexing script
python.exe .\core\index_chromadb_json.py .\knowledge-base\agent\

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Database indexing failed!
    echo Check that:
    echo   1. Python is installed and in PATH
    echo   2. Required packages are installed (pip install -r requirements.txt)
    echo   3. OPENAI_API_KEY is set in .env
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Database Built Successfully!
echo ========================================
echo.
echo ChromaDB vector database has been created at:
echo   knowledge-base\agent\chroma_db\
echo.
echo You can now:
echo   1. Test locally: start-backend.bat
echo   2. Deploy: build-backend.bat then deploy-backend.bat
echo.
pause

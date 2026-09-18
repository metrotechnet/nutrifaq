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

REM Check if nutrifaq-dbase exists
if not exist "nutrifaq-dbase" (
    echo [ERROR] nutrifaq-dbase folder not found!
    echo Please ensure the repository is complete.
    echo.
    pause
    exit /b 1
)

REM Check if transcripts folder has files
if not exist "nutrifaq-dbase\transcripts\*.*" (
    if not exist "nutrifaq-dbase\documents\*.*" (
        echo [ERROR] No documents found in nutrifaq-dbase\transcripts or documents
        echo Please add your documents first.
        echo.
        pause
        exit /b 1
    )
)

echo [INFO] Generating transcripts_chromadb.json from source documents...
echo.

REM Generate transcripts_chromadb.json from transcripts and documents
python.exe .\api\db_pipeline\generate_transcripts_json.py .\nutrifaq-dbase\

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed to generate transcripts_chromadb.json!
    echo Check that:
    echo   1. You have added documents to nutrifaq-dbase\transcripts\ or documents\
    echo   2. Python is installed and in PATH
    echo.
    pause
    exit /b 1
)

echo.
echo [INFO] Indexing documents to ChromaDB...
echo.

REM Run the indexing script
python.exe .\api\db_pipeline\index_chromadb_json.py .\nutrifaq-dbase\

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Database indexing failed!
    echo Check that:
    echo   1. Python is installed and in PATH
    echo   2. Required packages are installed (pip install -r requirements.txt)
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
echo   nutrifaq-dbase\chroma_db\
echo.
echo You can now:
echo   1. Test locally: start-backend.bat
echo   2. Deploy: build-backend.bat then deploy-backend.bat
echo.
pause

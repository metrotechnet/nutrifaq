@echo off
setlocal
REM ==================================================
REM Index local Nutria knowledge base into ChromaDB
REM Usage: index-database.bat [project_name] [collection_name]
REM Example: index-database.bat nutria nutrifaq-collection
REM ==================================================

set "PROJECT_NAME=%~1"
if "%PROJECT_NAME%"=="" set "PROJECT_NAME=nutria"

set "COLLECTION_NAME=%~2"
if "%COLLECTION_NAME%"=="" set "COLLECTION_NAME=nutrifaq-collection"

set "KB_ROOT=%~dp0nutrifaq-dbase"
set "VECTOR_DB_DIRNAME=chroma_db"

echo.
echo ========================================
echo   Indexing project: %PROJECT_NAME%
echo   Collection: %COLLECTION_NAME%
echo   KB root: %KB_ROOT%
echo ========================================
echo.

if not exist "%KB_ROOT%\%PROJECT_NAME%\documents" (
    echo [ERROR] Missing documents folder: %KB_ROOT%\%PROJECT_NAME%\documents
    echo Copy your knowledge base first, then rerun this script.
    exit /b 1
)

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_BIN=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_BIN=python"
)

set "KNOWLEDGE_BASE_ROOT=%KB_ROOT%"
set "VECTOR_DB_DIRNAME=%VECTOR_DB_DIRNAME%"

"%PYTHON_BIN%" -m api.index_chromadb "%PROJECT_NAME%" "%COLLECTION_NAME%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] Indexing failed with exit code %EXIT_CODE%.
    exit /b %EXIT_CODE%
)

echo.
echo [OK] Indexing completed successfully.
exit /b 0

@echo off
setlocal
REM ==================================================
REM Run the local knowledge base regeneration pipeline
REM Usage: index-database.bat [project_name]
REM Example: index-database.bat nutrifaq
REM ==================================================

set "PROJECT_NAME=%~1"
if "%PROJECT_NAME%"=="" set "PROJECT_NAME=nutrifaq"

set "KB_ROOT=%~dp0nutrifaq-dbase"
set "VECTOR_DB_DIRNAME=chroma_db"

echo.
echo ========================================
echo   Regenerating project: %PROJECT_NAME%
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

"%PYTHON_BIN%" -m api.db_pipeline.generate_transcripts_json "%KB_ROOT%"
set "EXIT_CODE=%ERRORLEVEL%"

if "%EXIT_CODE%"=="0" (
    "%PYTHON_BIN%" -m api.db_pipeline.index_chromadb_json "%KB_ROOT%"
    set "EXIT_CODE=%ERRORLEVEL%"
)

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] Regeneration failed with exit code %EXIT_CODE%.
    exit /b %EXIT_CODE%
)

echo.
    echo [OK] Regeneration completed successfully.
exit /b 0

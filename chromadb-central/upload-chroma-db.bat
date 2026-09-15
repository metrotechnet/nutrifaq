@echo off
REM ====================================
REM Upload ChromaDB files to GCS bucket
REM Usage:
REM   upload-chroma-db.bat                   Upload all projects
REM   upload-chroma-db.bat nutria            Upload only nutria
REM   upload-chroma-db.bat nutria --reload   Upload nutria + call /reload
REM   upload-chroma-db.bat --reload          Upload all + call /reload
REM ====================================
echo.

REM Parse arguments
set "TARGET_PROJECT="
set "DO_RELOAD=0"
for %%A in (%*) do (
    if /i "%%A"=="--reload" (
        set DO_RELOAD=1
    ) else (
        set "TARGET_PROJECT=%%A"
    )
)

REM Load configuration from .env file
if not exist ".env" (
    echo ERROR: .env file not found!
    pause
    exit /b 1
)

for /f "tokens=1,2 delims==" %%a in ('findstr /b "GCP_PROJECT_ID=" .env') do set GCP_PROJECT_ID=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "GCP_SERVICE_NAME=" .env') do set GCP_SERVICE_NAME=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "GCP_REGION=" .env') do set GCP_REGION=%%b

if "%GCP_PROJECT_ID%"=="" (
    echo ERROR: GCP_PROJECT_ID not found in .env file!
    pause
    exit /b 1
)

set BUCKET_NAME=agent-factory-database
set KB_DIR=knowledge-base

if defined TARGET_PROJECT (
    echo ====================================
    echo Uploading %TARGET_PROJECT% to gs://%BUCKET_NAME%
    echo ====================================
) else (
    echo ====================================
    echo Uploading ALL projects to gs://%BUCKET_NAME%
    echo ====================================
)
echo.

REM Upload single project or all projects
if defined TARGET_PROJECT (
    if exist "%KB_DIR%\%TARGET_PROJECT%\chroma_db" (
        echo Clearing gs://%BUCKET_NAME%/%TARGET_PROJECT%/chroma_db ...
        call gcloud storage rm "gs://%BUCKET_NAME%/%TARGET_PROJECT%/chroma_db/**" --recursive 2>nul
        echo Uploading %TARGET_PROJECT%/chroma_db ...
        call gcloud storage cp "%KB_DIR%\%TARGET_PROJECT%\chroma_db" "gs://%BUCKET_NAME%/%TARGET_PROJECT%/chroma_db" --recursive
        if errorlevel 1 (
            echo ERROR: Failed to upload %TARGET_PROJECT%/chroma_db
        ) else (
            echo OK: %TARGET_PROJECT%/chroma_db uploaded.
        )
    ) else (
        echo ERROR: %KB_DIR%\%TARGET_PROJECT%\chroma_db not found!
        pause
        exit /b 1
    )
) else (
    for /d %%P in (%KB_DIR%\*) do (
        set "PROJECT=%%~nxP"
        setlocal enabledelayedexpansion
        if exist "%%P\chroma_db" (
            echo Clearing gs://%BUCKET_NAME%/!PROJECT!/chroma_db ...
            call gcloud storage rm "gs://%BUCKET_NAME%/!PROJECT!/chroma_db/**" --recursive 2>nul
            echo Uploading !PROJECT!/chroma_db ...
            call gcloud storage cp "%%P\chroma_db" "gs://%BUCKET_NAME%/!PROJECT!/chroma_db" --recursive
            if errorlevel 1 (
                echo ERROR: Failed to upload !PROJECT!/chroma_db
                endlocal
            ) else (
                echo OK: !PROJECT!/chroma_db uploaded.
                endlocal
            )
        ) else (
            echo SKIP: !PROJECT! has no chroma_db folder.
            endlocal
        )
    )
)

REM Call /reload endpoint if requested
if "%DO_RELOAD%"=="1" (
    echo.
    echo ====================================
    echo Calling /reload on Cloud Run...
    echo ====================================
    if not "%GCP_SERVICE_NAME%"=="" if not "%GCP_REGION%"=="" (
        for /f "tokens=*" %%U in ('gcloud run services describe %GCP_SERVICE_NAME% --region=%GCP_REGION% --project=%GCP_PROJECT_ID% --format="value(status.url)" 2^>nul') do set "SERVICE_URL=%%U"
    )
    if not defined SERVICE_URL (
        echo WARNING: Could not resolve Cloud Run URL. Using localhost.
        set "SERVICE_URL=http://localhost:8080"
    )
    if defined TARGET_PROJECT (
        echo Reloading project: %TARGET_PROJECT%
        curl -s -X POST "%SERVICE_URL%/reload?project_name=%TARGET_PROJECT%"
    ) else (
        echo Reloading all projects...
        curl -s -X POST "%SERVICE_URL%/reload"
    )
    echo.
)

echo.
echo ====================================
echo Upload complete.
echo ====================================
pause

@echo off
setlocal enabledelayedexpansion
echo ====================================
echo Deploying IMX Agent Factory
echo ====================================
echo.

echo.
echo Loading deployment configuration from .env file...

REM Check if .env file exists
if not exist ".env" (
    echo ERROR: .env file not found!
    exit /b 1
)

REM Load all configuration from .env file (skip comment lines and empty lines)
for /f "usebackq eol=# tokens=1* delims==" %%a in (.env) do (
    if "%%a"=="AI_GATEWAY_API_KEY" set "CONFIG_AI_GATEWAY_KEY=%%b"
    if "%%a"=="OPENAI_API_KEY" set "CONFIG_OPENAI_KEY=%%b"
    if "%%a"=="GDRIVE_FOLDER_ID" set "GDRIVE_FOLDER_ID=%%b"
    if "%%a"=="GCP_PROJECT_ID" set "GCP_PROJECT=%%b"
    if "%%a"=="GCP_REGION" set "GCP_REGION=%%b"
    if "%%a"=="GCP_SERVICE_NAME" set "GCP_SERVICE_NAME=%%b"
    if "%%a"=="GCP_IMAGE_NAME" set "GCP_IMAGE_NAME=%%b"
    if "%%a"=="CLOUD_RUN_MEMORY" set "CLOUD_RUN_MEMORY=%%b"
    if "%%a"=="CLOUD_RUN_TIMEOUT" set "CLOUD_RUN_TIMEOUT=%%b"
    if "%%a"=="CLOUD_RUN_MIN_INSTANCES" set "CLOUD_RUN_MIN_INSTANCES=%%b"
    if "%%a"=="CLOUD_RUN_MAX_INSTANCES" set "CLOUD_RUN_MAX_INSTANCES=%%b"
    if "%%a"=="FIREBASE_PROJECT_ID" set "FIREBASE_PROJECT_ID=%%b"
    if "%%a"=="ADDITIONAL_CORS_ORIGINS" set "ADDITIONAL_CORS_ORIGINS=%%b"
    if "%%a"=="CHROMADB_CENTRAL_URL" set "CHROMADB_CENTRAL_URL=%%b"
    if "%%a"=="CLOUD_RUN_CPU" set "CLOUD_RUN_CPU=%%b"
    if "%%a"=="GCS_BUCKET_NAME" set "GCS_BUCKET_NAME=%%b"
    if "%%a"=="ADMIN_ACCESS_KEY" set "ADMIN_ACCESS_KEY=%%b"


)

echo.
echo Configuration loaded:
echo   Project: %GCP_PROJECT%
echo   Region: %GCP_REGION%
echo   Service: %GCP_SERVICE_NAME%
echo   Image: %GCP_IMAGE_NAME%
echo   Memory: %CLOUD_RUN_MEMORY%
echo   Timeout: %CLOUD_RUN_TIMEOUT%s
echo   Min Instances: %CLOUD_RUN_MIN_INSTANCES%
echo   Max Instances: %CLOUD_RUN_MAX_INSTANCES%
echo   Firebase Project: %FIREBASE_PROJECT_ID%
echo.

REM Validate configuration
if "%GCP_PROJECT%"=="" (
    echo ERROR: GCP_PROJECT_ID not found in .env file!
    exit /b 1
)
if "%GCP_REGION%"=="" (
    echo ERROR: GCP_REGION not found in .env file!
    exit /b 1
)
if "%CONFIG_AI_GATEWAY_KEY%"=="" (
    echo ERROR: AI_GATEWAY_API_KEY not found in .env file!
    exit /b 1
)
if "%GCP_SERVICE_NAME%"=="" (
    echo ERROR: GCP_SERVICE_NAME not found in .env file!
    exit /b 1
)
if "%GCP_IMAGE_NAME%"=="" (
    echo ERROR: GCP_IMAGE_NAME not found in .env file!
    exit /b 1
)

REM Set defaults for optional parameters
if "%CLOUD_RUN_MEMORY%"=="" set CLOUD_RUN_MEMORY=1Gi
if "%CLOUD_RUN_TIMEOUT%"=="" set CLOUD_RUN_TIMEOUT=300
if "%CLOUD_RUN_MIN_INSTANCES%"=="" set CLOUD_RUN_MIN_INSTANCES=0
if "%CLOUD_RUN_MAX_INSTANCES%"=="" set CLOUD_RUN_MAX_INSTANCES=10

REM Use API keys from configuration file
set AI_GATEWAY_API_KEY=%CONFIG_AI_GATEWAY_KEY%
set OPENAI_API_KEY=%CONFIG_OPENAI_KEY%

echo.
echo Starting deployment to Cloud Run...
echo.

REM Deploy to Cloud Run
call gcloud run deploy %GCP_SERVICE_NAME% ^
  --image %GCP_IMAGE_NAME% ^
  --platform managed ^
  --region %GCP_REGION% ^
  --allow-unauthenticated ^
  --set-env-vars "AI_GATEWAY_API_KEY=%AI_GATEWAY_API_KEY%,OPENAI_API_KEY=%OPENAI_API_KEY%,GCP_PROJECT_ID=%GCP_PROJECT%,GCP_REGION=%GCP_REGION%,GDRIVE_FOLDER_ID=%GDRIVE_FOLDER_ID%,FIREBASE_PROJECT_ID=%FIREBASE_PROJECT_ID%,ADDITIONAL_CORS_ORIGINS=%ADDITIONAL_CORS_ORIGINS%,CHROMADB_CENTRAL_URL=%CHROMADB_CENTRAL_URL%,GCS_BUCKET_NAME=%GCS_BUCKET_NAME%,ADMIN_ACCESS_KEY=%ADMIN_ACCESS_KEY%" ^
  --update-secrets /secrets/gdrive/credentials.json=gdrive-credentials:latest ^
  --memory %CLOUD_RUN_MEMORY% ^
  --timeout %CLOUD_RUN_TIMEOUT%s ^
  --min-instances %CLOUD_RUN_MIN_INSTANCES% ^
  --max-instances %CLOUD_RUN_MAX_INSTANCES% ^
  --cpu %CLOUD_RUN_CPU% ^
  --concurrency 80 ^
  --execution-environment gen1


if !ERRORLEVEL! NEQ 0 (
    echo.
    echo ERROR: Cloud Run deployment failed with exit code !ERRORLEVEL!
    exit /b 1
)

echo.
echo ====================================
echo SUCCESS: Deployment completed!
echo ====================================
echo.

REM Get service URL
echo Retrieving service URL...
for /f "usebackq tokens=*" %%i in (`gcloud run services describe %GCP_SERVICE_NAME% --region^=%GCP_REGION% --format^="value(status.url)"`) do set SERVICE_URL=%%i

if "!SERVICE_URL!"=="" (
    echo WARNING: Could not retrieve service URL automatically
    echo Please check Cloud Run console for the service URL
    exit /b 0
)

echo Service URL: !SERVICE_URL!
echo.

REM Save backend URL for frontend deployment
echo Saving backend URL for frontend deployment...
echo !SERVICE_URL!> .backend-url.tmp
echo   - Saved to .backend-url.tmp
echo.

REM Update .env file with BACKEND_URL
echo Updating .env file with BACKEND_URL...
powershell -Command "$url='!SERVICE_URL!'; $content = Get-Content .env; $updated = $false; $newContent = @(); foreach ($line in $content) { if ($line -match '^BACKEND_URL=') { $newContent += \"BACKEND_URL=$url\"; $updated = $true } else { $newContent += $line } }; if (-not $updated) { $newContent += \"BACKEND_URL=$url\" }; $newContent | Set-Content .env"
echo   - .env file updated with BACKEND_URL=!SERVICE_URL!
echo.

echo ====================================
echo 🚀 Your application is now live!
echo ====================================
echo.
echo Backend URL: !SERVICE_URL!
echo.
echo Next step: Run deploy-frontend.bat to deploy the frontend
echo.
@echo off
REM ====================================
REM Deploy ChromaDB Central API to GCP Cloud Run
REM ====================================
echo.

REM Load configuration from .env file
if not exist ".env" (
    echo ERROR: .env file not found!
    pause
    exit /b 1
)

REM Load project name, image name, region, and service name from .env

for /f "tokens=1,2 delims==" %%a in ('findstr /b "GCP_PROJECT_ID=" .env') do set GCP_PROJECT_ID=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "GCP_IMAGE_NAME=" .env') do set GCP_IMAGE_NAME=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "GCP_REGION=" .env') do set GCP_REGION=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "GCP_SERVICE_NAME=" .env') do set GCP_SERVICE_NAME=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "GCP_MEMORY=" .env') do set GCP_MEMORY=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "GCP_CPU=" .env') do set GCP_CPU=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "GCP_MAX_INSTANCES=" .env') do set GCP_MAX_INSTANCES=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "GCP_MIN_INSTANCES=" .env') do set GCP_MIN_INSTANCES=%%b

REM Load app environment variables for Cloud Run
for /f "tokens=1,2 delims==" %%a in ('findstr /b "OPENAI_API_KEY=" .env') do set OPENAI_API_KEY=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "AI_GATEWAY_API_KEY=" .env') do set AI_GATEWAY_API_KEY=%%b


REM Validate configuration
if "%GCP_PROJECT_ID%"=="" (
    echo ERROR: GCP_PROJECT_ID not found in .env file!
    pause
    exit /b 1
)
if "%GCP_IMAGE_NAME%"=="" (
    echo ERROR: GCP_IMAGE_NAME not found in .env file!
    pause
    exit /b 1
)
if "%GCP_REGION%"=="" (
    echo ERROR: GCP_REGION not found in .env file!
    pause
    exit /b 1
)
if "%GCP_SERVICE_NAME%"=="" (
    echo ERROR: GCP_SERVICE_NAME not found in .env file!
    pause
    exit /b 1
)

echo Project: %GCP_PROJECT_ID%
echo Image: %GCP_IMAGE_NAME%
echo Region: %GCP_REGION%
echo Service: %GCP_SERVICE_NAME%
echo.

echo Deploying to Cloud Run...
gcloud run deploy %GCP_SERVICE_NAME% --image %GCP_IMAGE_NAME% --region %GCP_REGION% --platform managed --no-allow-unauthenticated --project=%GCP_PROJECT_ID% --memory=%GCP_MEMORY% --cpu=%GCP_CPU% --max-instances=%GCP_MAX_INSTANCES% --min-instances=%GCP_MIN_INSTANCES% --set-env-vars="OPENAI_API_KEY=%OPENAI_API_KEY%,AI_GATEWAY_API_KEY=%AI_GATEWAY_API_KEY%"
set DEPLOY_STATUS=%ERRORLEVEL%
if %DEPLOY_STATUS% NEQ 0 (
    echo.
    echo ❌ Cloud Run deployment failed!
    echo 🔍 Troubleshooting steps:
    echo 1. Check if you have Cloud Run API enabled
    echo 2. Verify IAM permissions (Cloud Run Admin role)
    echo 3. Check if billing is enabled for the project
    echo 4. Try: gcloud auth login --update-adc
    echo.
    pause
    exit /b 1
)
gcloud run services add-iam-policy-binding %GCP_SERVICE_NAME% --member=serviceAccount:backend@%GCP_PROJECT_ID%.iam.gserviceaccount.com --role=roles/run.invoker
echo.
echo ✅ Deployment completed successfully!
echo 🌐 Service deployed: %GCP_SERVICE_NAME% in region %GCP_REGION%
echo.
exit /b 0

@echo off
REM ====================================
REM Setup Cloud Scheduler for Daily DB Update
REM ====================================
echo.

REM Load configuration from .env file
if not exist ".env" (
    echo ERROR: .env file not found!
    pause
    exit /b 1
)

for /f "tokens=1,2 delims==" %%a in ('findstr /b "GCP_PROJECT_ID=" .env') do set GCP_PROJECT_ID=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "GCP_REGION=" .env') do set GCP_REGION=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "GCP_SERVICE_NAME=" .env') do set GCP_SERVICE_NAME=%%b

REM Enable Cloud Scheduler API
echo [1/4] Enabling Cloud Scheduler API...
call gcloud services enable cloudscheduler.googleapis.com --project=%GCP_PROJECT_ID% --quiet

REM Get the Cloud Run service URL
echo [2/4] Getting Cloud Run service URL...
for /f %%i in ('gcloud run services describe %GCP_SERVICE_NAME% --region %GCP_REGION% --project=%GCP_PROJECT_ID% --format="value(status.url)"') do set SERVICE_URL=%%i

if "%SERVICE_URL%"=="" (
    echo ERROR: Could not get Cloud Run service URL. Is the service deployed?
    pause
    exit /b 1
)
echo Service URL: %SERVICE_URL%

REM Create a service account for the scheduler (if not exists)
echo [3/4] Setting up scheduler service account...
call gcloud iam service-accounts create scheduler-invoker --display-name="Cloud Scheduler Invoker" --project=%GCP_PROJECT_ID% 2>nul

REM Grant the service account permission to invoke Cloud Run
call gcloud run services add-iam-policy-binding %GCP_SERVICE_NAME% --member="serviceAccount:scheduler-invoker@%GCP_PROJECT_ID%.iam.gserviceaccount.com" --role="roles/run.invoker" --region=%GCP_REGION% --project=%GCP_PROJECT_ID% --quiet

REM Create the scheduled job: daily at 3 AM Montreal time
echo [4/4] Creating Cloud Scheduler job...
call gcloud scheduler jobs delete update-nutria-db --location=%GCP_REGION% --project=%GCP_PROJECT_ID% --quiet 2>nul

gcloud scheduler jobs create http update-nutria-db ^
    --location=%GCP_REGION% ^
    --schedule="0 3 * * *" ^
    --time-zone="America/Montreal" ^
    --uri="%SERVICE_URL%/update?project_name=nutria&collection_name=gdrive_documents&folder_id=1SLix2RmU1cwf1Qt-06C5DD0Q43ASgPqA" ^
    --http-method=POST ^
    --oidc-service-account-email="scheduler-invoker@%GCP_PROJECT_ID%.iam.gserviceaccount.com" ^
    --oidc-token-audience="%SERVICE_URL%" ^
    --attempt-deadline=1800s ^
    --project=%GCP_PROJECT_ID%

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Failed to create scheduler job!
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Cloud Scheduler Setup Complete!
echo ========================================
echo.
echo Job: update-nutria-db
echo Schedule: Daily at 3:00 AM (America/Montreal)
echo Target: %SERVICE_URL%/update?project_name=nutria^&collection_name=gdrive_documents^&folder_id=1SLix2RmU1cwf1Qt-06C5DD0Q43ASgPqA
echo.
echo To test manually:
echo   gcloud scheduler jobs run update-nutria-db --location=%GCP_REGION% --project=%GCP_PROJECT_ID%
echo.
pause

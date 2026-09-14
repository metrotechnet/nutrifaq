@echo off
echo ====================================
echo Building IMX Agent (GCP Cloud Build)
echo ====================================
echo.

REM Load configuration from .env file
echo Loading configuration from .env file...

if not exist ".env" (
    echo ERROR: .env file not found!
    pause
    exit /b 1
)

REM Load project name and image name from .env
for /f "tokens=1,2 delims==" %%a in ('findstr /b "GCP_PROJECT_ID=" .env') do set GCP_PROJECT_ID=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "GCP_IMAGE_NAME=" .env') do set GCP_IMAGE_NAME=%%b

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

echo Project: %GCP_PROJECT_ID%
echo Image: %GCP_IMAGE_NAME%
echo.

echo [1/4] Validating project structure...
if not exist "Dockerfile" (
    echo ERROR: Dockerfile not found!
    pause
    exit /b 1
)

if not exist "requirements.txt" (
    echo ERROR: requirements.txt not found!
    pause
    exit /b 1
)

if not exist "app.py" (
    echo ERROR: app.py not found!
    pause
    exit /b 1
)

echo [2/4] Setting up GCP project and enabling APIs...
echo Setting project to %GCP_PROJECT_ID%...
echo Before setting project...
call gcloud config set project %GCP_PROJECT_ID% --quiet
echo Project set command finished.
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to set GCP project
    pause
    exit /b 1
)

echo Starting API enablement...
call gcloud services enable cloudbuild.googleapis.com containerregistry.googleapis.com run.googleapis.com --project=%GCP_PROJECT_ID% --quiet
echo API enablement command finished with ERRORLEVEL=%ERRORLEVEL%
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to enable APIs
    pause
    exit /b 1
)
echo APIs enabled successfully.

echo [3/4] Granting Cloud Build service account permissions...
echo Getting project number for %GCP_PROJECT_ID%...
set PROJECT_NUMBER=
for /f %%i in ('gcloud projects describe %GCP_PROJECT_ID% --format="value(projectNumber)"') do set PROJECT_NUMBER=%%i
echo Project number: %PROJECT_NUMBER%
if "%PROJECT_NUMBER%"=="" (
    echo ERROR: Failed to get project number
    pause
    exit /b 1
)

echo Adding IAM policy bindings...
echo Granting roles/run.admin to Cloud Build SA...
call gcloud projects add-iam-policy-binding %GCP_PROJECT_ID% --member="serviceAccount:%PROJECT_NUMBER%@cloudbuild.gserviceaccount.com" --role="roles/run.admin" --quiet
echo roles/run.admin granted. ERRORLEVEL=%ERRORLEVEL%
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to add run.admin role
    pause
    exit /b 1
)

echo Granting roles/iam.serviceAccountUser to Cloud Build SA...
call gcloud projects add-iam-policy-binding %GCP_PROJECT_ID% --member="serviceAccount:%PROJECT_NUMBER%@cloudbuild.gserviceaccount.com" --role="roles/iam.serviceAccountUser" --quiet
echo roles/iam.serviceAccountUser granted. ERRORLEVEL=%ERRORLEVEL%
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to add serviceAccountUser role
    pause
    exit /b 1
)
echo Permissions granted successfully.

echo [4/4] Building with Google Cloud Build...
echo Starting Cloud Build submit...
gcloud builds submit --tag %GCP_IMAGE_NAME% --timeout=20m --machine-type=e2-highcpu-8 --project=%GCP_PROJECT_ID%
set BUILD_STATUS=%ERRORLEVEL%
echo Cloud Build submit finished with ERRORLEVEL=%BUILD_STATUS%

if %BUILD_STATUS% NEQ 0 (
    echo.
    echo ❌ Cloud Build failed! 
    echo 🔍 Troubleshooting steps:
    echo 1. Check if you have Cloud Build API enabled
    echo 2. Verify IAM permissions (Cloud Build Editor role)
    echo 3. Check if billing is enabled for the project
    echo 4. Try: gcloud auth login --update-adc
    echo.
    pause
    exit /b 1
)

echo.
echo ✅ Build completed successfully!
echo 🚀 Docker image ready: %GCP_IMAGE_NAME%
echo 📋 Next step: Run deploy.bat to deploy to Cloud Run
echo.
exit /b 0
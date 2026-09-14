@echo off
setlocal enabledelayedexpansion
echo [DEBUG] Started
echo ====================================
echo Deploying IMX Frontend to Firebase
echo ====================================
echo.

REM Check if Firebase CLI is installed
where firebase >nul 2>nul
if !errorlevel! neq 0 (
    echo ERROR: Firebase CLI is not installed!
    echo Please install it using: npm install -g firebase-tools
    exit /b 1
)

REM Check if .env file exists
if not exist ".env" (
    echo ERROR: .env file not found!
    exit /b 1
)

REM Load Firebase project ID from .env
for /f "tokens=1,2 delims==" %%a in ('findstr /b "FIREBASE_PROJECT_ID=" .env') do set FIREBASE_PROJECT=%%b
if "!FIREBASE_PROJECT!"=="" (
    echo ERROR: FIREBASE_PROJECT_ID not found in .env file!
    exit /b 1
)

echo Setting Firebase project to: !FIREBASE_PROJECT!
call firebase use !FIREBASE_PROJECT!
if !errorlevel! neq 0 (
    echo ERROR: Failed to set Firebase project!
    exit /b 1
)
echo.

REM Load backend URL
for /f "tokens=1,2 delims==" %%a in ('findstr /b "BACKEND_URL=" .env 2^>nul') do set BACKEND_URL=%%b
if "!BACKEND_URL!"=="" if exist ".backend-url.tmp" set /p BACKEND_URL=<.backend-url.tmp
if "!BACKEND_URL!"=="" set BACKEND_URL=http://localhost:8080

echo Backend URL: !BACKEND_URL!
echo.

REM Load Firebase and App Check configuration from .env
for /f "tokens=1,2 delims==" %%a in ('findstr /b "FIREBASE_API_KEY=" .env 2^>nul') do set FIREBASE_API_KEY=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "FIREBASE_APP_ID=" .env 2^>nul') do set FIREBASE_APP_ID=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "FIREBASE_AUTH_DOMAIN=" .env 2^>nul') do set FIREBASE_AUTH_DOMAIN=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "FIREBASE_STORAGE_BUCKET=" .env 2^>nul') do set FIREBASE_STORAGE_BUCKET=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "FIREBASE_MESSAGING_SENDER_ID=" .env 2^>nul') do set FIREBASE_MESSAGING_SENDER_ID=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "FIREBASE_MEASUREMENT_ID=" .env 2^>nul') do set FIREBASE_MEASUREMENT_ID=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "RECAPTCHA_SITE_KEY=" .env 2^>nul') do set RECAPTCHA_SITE_KEY=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "APP_CHECK_ENABLED=" .env 2^>nul') do set APP_CHECK_ENABLED=%%b
for /f "tokens=1,2 delims==" %%a in ('findstr /b "APP_CHECK_DEBUG_TOKEN=" .env 2^>nul') do set APP_CHECK_DEBUG_TOKEN=%%b

REM Set defaults for Firebase values if not in .env
if "!FIREBASE_AUTH_DOMAIN!"=="" set FIREBASE_AUTH_DOMAIN=!FIREBASE_PROJECT!.firebaseapp.com
if "!FIREBASE_STORAGE_BUCKET!"=="" set FIREBASE_STORAGE_BUCKET=!FIREBASE_PROJECT!.firebasestorage.app
if "!FIREBASE_MESSAGING_SENDER_ID!"=="" set FIREBASE_MESSAGING_SENDER_ID=1075445091126
if "!FIREBASE_MEASUREMENT_ID!"=="" set FIREBASE_MEASUREMENT_ID=G-0Q9L0RSCF3

REM Set defaults if not found
if "!FIREBASE_API_KEY!"=="" (
    echo ERROR: FIREBASE_API_KEY not found in .env file!
    exit /b 1
)
if "!FIREBASE_APP_ID!"=="" (
    echo ERROR: FIREBASE_APP_ID not found in .env file!
    exit /b 1
)
if "!RECAPTCHA_SITE_KEY!"=="" (
    echo ERROR: RECAPTCHA_SITE_KEY not found in .env file!
    exit /b 1
)
if "!APP_CHECK_ENABLED!"=="" set APP_CHECK_ENABLED=false
if "!APP_CHECK_DEBUG_TOKEN!"=="" set APP_CHECK_DEBUG_TOKEN=

echo Firebase Project: !FIREBASE_PROJECT!
echo Firebase API Key: !FIREBASE_API_KEY:~0,20!...
echo Firebase App ID: !FIREBASE_APP_ID:~0,30!...
echo Auth Domain: !FIREBASE_AUTH_DOMAIN!
echo Storage Bucket: !FIREBASE_STORAGE_BUCKET!
echo reCAPTCHA Site Key: !RECAPTCHA_SITE_KEY:~0,20!...
echo App Check Enabled: !APP_CHECK_ENABLED!
if not "!APP_CHECK_DEBUG_TOKEN!"=="" echo Debug Token: !APP_CHECK_DEBUG_TOKEN:~0,20!...
echo.

REM Create and copy files
if not exist "public" mkdir public
if not exist "public\static" mkdir public\static

copy /Y "templates\index.html" "public\index.html" >nul
if !errorlevel! neq 0 (
    echo ERROR: Failed to copy index.html
    exit /b 1
)
copy /Y "templates\log_report.html" "public\log_report.html" >nul
if !errorlevel! neq 0 (
    echo ERROR: Failed to copy log_report.html
    exit /b 1
)
REM Inject Firebase configuration into HTML
echo Injecting Firebase configuration...
powershell -Command "(Get-Content 'public\index.html') -replace '{{FIREBASE_PROJECT_ID}}', '!FIREBASE_PROJECT!' -replace '{{FIREBASE_API_KEY}}', '!FIREBASE_API_KEY!' -replace '{{FIREBASE_AUTH_DOMAIN}}', '!FIREBASE_AUTH_DOMAIN!' -replace '{{FIREBASE_STORAGE_BUCKET}}', '!FIREBASE_STORAGE_BUCKET!' -replace '{{FIREBASE_MESSAGING_SENDER_ID}}', '!FIREBASE_MESSAGING_SENDER_ID!' -replace '{{FIREBASE_APP_ID}}', '!FIREBASE_APP_ID!' -replace '{{FIREBASE_MEASUREMENT_ID}}', '!FIREBASE_MEASUREMENT_ID!' -replace '{{RECAPTCHA_SITE_KEY}}', '!RECAPTCHA_SITE_KEY!' -replace '{{APP_CHECK_ENABLED}}', '!APP_CHECK_ENABLED!' -replace '{{APP_CHECK_DEBUG_TOKEN}}', '!APP_CHECK_DEBUG_TOKEN!' | Set-Content 'public\index.html'"
if !errorlevel! neq 0 (
    echo ERROR: Failed to inject Firebase configuration!
    exit /b 1
)

REM Inject backend URL into backend-url.js
xcopy /Y /E /I "static\*" "public\static\" >nul
if !errorlevel! neq 0 (
    echo ERROR: Failed to copy static files
    exit /b 1
)

powershell -Command "(Get-Content 'public\index.html') -replace '/static/', 'static/' | Set-Content 'public\index.html'"
echo window.BACKEND_URL = '!BACKEND_URL!'; > "public\static\js\backend-url.js"

REM Inject backend URL into log_report.html
powershell -Command "(Get-Content 'public\log_report.html') -replace '{{BACKEND_URL}}', '!BACKEND_URL!' | Set-Content 'public\log_report.html'"

echo Files prepared successfully!
echo.
echo Deploying to Firebase...
call firebase deploy --only hosting
if !errorlevel! equ 0 (
    echo.
    echo Deployment successful!
) else (
    echo.
    echo ERROR: Deployment failed!
    exit /b 1
)

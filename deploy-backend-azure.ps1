param(
    [string]$ResourceGroup = "nutrifaq-rg",
    [string]$Location = "eastus",
    [string]$PlanName = "nutrifaq-plan",
    [string]$AppName = "nutrifaq-chat",
    [string]$Sku = "B1",
    [string]$Runtime = "PYTHON|3.11",
    [string]$ZipPath = "app.zip",
    [switch]$KeepArtifact
)

$ErrorActionPreference = "Stop"

Write-Host "== NutriFAQ Azure deployment =="

# Ensure Azure CLI is installed
$azCmd = Get-Command az -ErrorAction SilentlyContinue
if (-not $azCmd) {
    throw "Azure CLI (az) is not installed or not on PATH. Install it first."
}

# Create the resource group if it does not exist
Write-Host "Creating resource group '$ResourceGroup' in '$Location'..."
az group create --name $ResourceGroup --location $Location | Out-Null

# Create the App Service plan if it does not exist
Write-Host "Ensuring App Service plan '$PlanName' exists..."
$planExists = az appservice plan list --resource-group $ResourceGroup --query "[?name=='$PlanName'] | length(@)" -o tsv
if ($planExists -eq "0") {
    az appservice plan create --name $PlanName --resource-group $ResourceGroup --location $Location --sku $Sku --is-linux | Out-Null
}

# Create the web app if it does not exist
Write-Host "Ensuring web app '$AppName' exists..."
$appExists = az webapp show --resource-group $ResourceGroup --name $AppName --query "name" -o tsv 2>$null
if (-not $appExists) {
    az webapp create --resource-group $ResourceGroup --plan $PlanName --name $AppName --runtime $Runtime | Out-Null
}

# Build zip excluding git/virtualenv/user-local folders
$zipBaseName = [System.IO.Path]::GetFileNameWithoutExtension($ZipPath)
$zipDir = [System.IO.Path]::GetDirectoryName($ZipPath)
if ([string]::IsNullOrWhiteSpace($zipDir)) {
    $zipDir = (Get-Location).Path
}
$zipArtifact = Join-Path $zipDir ("{0}-{1}.zip" -f $zipBaseName, (Get-Date -Format "yyyyMMdd-HHmmss"))

Write-Host "Packaging project into '$zipArtifact'..."

$pythonExe = if (Test-Path -LiteralPath "$PSScriptRoot\.venv\Scripts\python.exe") {
    "$PSScriptRoot\.venv\Scripts\python.exe"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    (Get-Command python).Source
} else {
    throw "Python could not be found. Install Python 3.11 or use the project's virtual environment."
}

$env:ZIP_PATH = $zipArtifact
$tempScript = Join-Path $env:TEMP "create_azure_zip.py"
@'
import os
import zipfile
from pathlib import Path

root = Path.cwd()
zip_path = Path(os.environ["ZIP_PATH"])
include = {"app.py", "__init__.py", "requirements.txt", "startup.sh"}
include_dirs = {"api", "static", "templates"}
exclude = {
    ".git", ".venv", "__pycache__", ".pytest_cache", ".azure", ".vs",
    ".vscode", ".firebase", "node_modules", "knowledge-base", "public",
    "doc", "build-backend.bat", "build-database.bat", "deploy-backend.bat",
    "deploy-frontend.bat", "deploy-gcp-backend.bat", "deploy-gcp-frontend.bat",
    "index-database.bat", "question_log.json", "app.zip"
}

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for entry in root.iterdir():
        if entry.name in exclude:
            continue
        if entry.name in include or (entry.is_dir() and entry.name in include_dirs):
            if entry.is_dir():
                for path in sorted(entry.rglob("*")):
                    if path.is_file() and not any(part in exclude for part in path.relative_to(root).parts):
                        zf.write(path, arcname=path.relative_to(root).as_posix())
            else:
                zf.write(entry, arcname=entry.name)
'@ | Set-Content -Path $tempScript -Encoding UTF8

& $pythonExe $tempScript

if ($LASTEXITCODE -ne 0) {
    throw "Failed to create the Azure deployment zip package."
}

# Configure app settings for the FastAPI app
Write-Host "Setting Azure app settings..."
$settingsMap = [ordered]@{
    WEBSITES_PORT = "8000"
    PORT = "8000"
    APP_CHECK_ENABLED = "false"
    KNOWLEDGE_BASE_ROOT = "/home/site/wwwroot/knowledge-base"
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
    ENABLE_ORYX_BUILD = "true"
}

$envFilePath = Join-Path $PSScriptRoot ".env"
if (Test-Path -LiteralPath $envFilePath) {
    Get-Content -LiteralPath $envFilePath | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }

        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) {
            return
        }

        $key = $parts[0].Trim()
        $value = $parts[1]
        if ($key) {
            $settingsMap[$key] = $value
        }
    }
    Write-Host "Loaded $($settingsMap.Count) app settings (including .env values)."
} else {
    Write-Host "No .env file found at '$envFilePath'. Using deployment defaults only."
}

$settingsArgs = $settingsMap.GetEnumerator() | ForEach-Object {
    "{0}={1}" -f $_.Key, $_.Value
}

az webapp config appsettings set --resource-group $ResourceGroup --name $AppName --settings $settingsArgs | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure Azure app settings."
}

# Configure startup command to run the FastAPI app via gunicorn + uvicorn workers
Write-Host "Setting startup command..."
az webapp config set --resource-group $ResourceGroup --name $AppName --startup-file "python -m pip install --no-cache-dir -r /home/site/wwwroot/requirements.txt && gunicorn --chdir /home/site/wwwroot --bind=0.0.0.0:8000 --timeout 120 -k uvicorn.workers.UvicornWorker app:app" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure Azure startup command."
}

# Deploy the zip to Azure App Service
Write-Host "Deploying to Azure App Service..."
az webapp deploy --resource-group $ResourceGroup --name $AppName --src-path $zipArtifact --type zip --clean true | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Az webapp deploy failed. See the Azure deployment logs for more detail."
}

# Restart the app
Write-Host "Restarting the app..."
az webapp restart --resource-group $ResourceGroup --name $AppName | Out-Null

if (-not $KeepArtifact -and (Test-Path -LiteralPath $zipArtifact)) {
    Remove-Item -LiteralPath $zipArtifact -Force
}

$siteUrl = "https://$AppName.azurewebsites.net"
Write-Host "Deployment complete."
Write-Host "Open: $siteUrl"
Write-Host "Health check: $siteUrl/health"

param(
    [string]$ResourceGroup = "nutrifaq-rg",
    [string]$Location = "canadacentral",
    [string]$PlanName = "nutrifaq-plan-cc",
    [string]$AppName = "nutrifaq-api",
    [string]$Sku = "B1",
    [string]$Runtime = "PYTHON:3.11",
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

# Ensure resource group exists
Write-Host "Ensuring resource group '$ResourceGroup' exists..."
$rgExists = az group exists --name $ResourceGroup --only-show-errors
if ($rgExists -eq "false") {
    Write-Host "Creating resource group '$ResourceGroup' in '$Location'..."
    az group create --name $ResourceGroup --location $Location | Out-Null
} else {
    Write-Host "Resource group '$ResourceGroup' already exists. Reusing it."
}

# Ensure App Service plan exists
Write-Host "Ensuring App Service plan '$PlanName' exists..."
$planExists = az appservice plan list --resource-group $ResourceGroup --query "[?name=='$PlanName'] | length(@)" -o tsv
if ($planExists -eq "0") {
    az appservice plan create --name $PlanName --resource-group $ResourceGroup --location $Location --sku $Sku --is-linux | Out-Null
}

# Reuse an existing app, otherwise create it
Write-Host "Ensuring web app '$AppName' exists..."
$showCmd = 'az webapp show --resource-group "{0}" --name "{1}" --query "name" -o tsv --only-show-errors' -f $ResourceGroup, $AppName
$appExists = cmd /d /c "$showCmd 2>NUL"
if ($LASTEXITCODE -ne 0) {
    $appExists = ""
}

if (-not $appExists) {
    $createCmd = 'az webapp create --resource-group "{0}" --plan "{1}" --name "{2}" --runtime "{3}" --only-show-errors' -f $ResourceGroup, $PlanName, $AppName, $Runtime
    $createOutput = cmd /d /c "$createCmd 2>&1"
    if ($createOutput) {
        $createOutput | ForEach-Object { Write-Host $_ }
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create Azure web app '$AppName'."
    }
} else {
    Write-Host "Web app '$AppName' already exists; reusing it."
}

# Minimal app settings
Write-Host "Setting basic app settings..."
$deployVersion = "az-$(Get-Date -Format yyyyMMdd-HHmmss)"
$settingsMap = [ordered]@{
    WEBSITES_PORT = "8000"
    PORT = "8000"
    APP_VERSION = $deployVersion
    WEBSITES_CONTAINER_START_TIME_LIMIT = "1800"
}

$settingsArgs = $settingsMap.GetEnumerator() | ForEach-Object {
    "{0}={1}" -f $_.Key, $_.Value
}
az webapp config appsettings set --resource-group $ResourceGroup --name $AppName --settings $settingsArgs | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure basic Azure app settings."
}

# Minimal startup command
Write-Host "Setting startup command..."
$startupCmd = "python -m pip install --no-cache-dir -r /home/site/wwwroot/requirements.txt && python /home/site/wwwroot/app.py"
az webapp config set --resource-group $ResourceGroup --name $AppName --startup-file $startupCmd | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure Azure startup command."
}

# Build zip artifact
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
$env:PROJECT_ROOT = $PSScriptRoot
$tempScript = Join-Path $env:TEMP "create_azure_zip.py"
@'
import os
import zipfile
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"]).resolve()
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

# Deploy zip
Write-Host "Deploying to Azure App Service..."
$deployOutput = az webapp deploy --resource-group $ResourceGroup --name $AppName --src-path $zipArtifact --type zip --clean true --only-show-errors 2>&1
if ($LASTEXITCODE -ne 0) {
    $deployOutput | ForEach-Object { Write-Host $_ }
    throw "Azure web app deploy failed."
}
if ($deployOutput) {
    $deployOutput | ForEach-Object { Write-Host $_ }
}

# Simple health check
$siteUrl = "https://$AppName.azurewebsites.net"
$healthUrl = "$siteUrl/health"
Write-Host "Checking health endpoint: $healthUrl"
try {
    $response = Invoke-WebRequest -Uri $healthUrl -Method Get -TimeoutSec 30 -UseBasicParsing
    if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
        Write-Host "Health check passed: HTTP $($response.StatusCode)"
    } else {
        Write-Warning "Health endpoint returned HTTP $($response.StatusCode)."
    }
} catch {
    Write-Warning "Health check did not return a successful response yet: $($_.Exception.Message)"
}

if (-not $KeepArtifact -and (Test-Path -LiteralPath $zipArtifact)) {
    Remove-Item -LiteralPath $zipArtifact -Force
}

Write-Host "Deployment complete."
Write-Host "App URL: $siteUrl"
Write-Host "Health URL: $healthUrl"

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
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
    ENABLE_ORYX_BUILD = "true"
    PIP_ROOT_USER_ACTION = "ignore"
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
$startupCmd = "python /home/site/wwwroot/app.py"
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
$previousNativeErrBehavior = $null
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $previousNativeErrBehavior = $PSNativeCommandUseErrorActionPreference
    $PSNativeCommandUseErrorActionPreference = $false
}

try {
    $deployOutput = az webapp deploy --resource-group $ResourceGroup --name $AppName --src-path $zipArtifact --type zip --clean true --only-show-errors 2>&1
    $deployText = ($deployOutput | Out-String)

    if ($LASTEXITCODE -ne 0) {
        if ($deployText -match "Status Code:\s*502") {
            Write-Warning "Azure deploy returned transient 502 from SCM. Verifying latest deployment status..."

            $deploymentConfirmed = $false
            $maxChecks = 8
            for ($check = 1; $check -le $maxChecks; $check++) {
                $latestDeploymentJson = az webapp deployment list --resource-group $ResourceGroup --name $AppName --query "[0].{id:id,status:status,message:message,end_time:end_time}" -o json --only-show-errors 2>$null
                if ($LASTEXITCODE -eq 0 -and $latestDeploymentJson) {
                    $latestDeployment = $latestDeploymentJson | ConvertFrom-Json
                    $statusValue = "{0}" -f $latestDeployment.status
                    Write-Host ("Deployment status check {0}/{1}: id={2} status={3}" -f $check, $maxChecks, $latestDeployment.id, $statusValue)

                    if ($statusValue -in @("4", "success", "Success", "succeeded", "Succeeded")) {
                        $deploymentConfirmed = $true
                        break
                    }

                    if ($statusValue -in @("3", "failed", "Failed")) {
                        break
                    }
                }

                Start-Sleep -Seconds 10
            }

            if (-not $deploymentConfirmed) {
                throw "Azure deploy returned 502 and latest deployment was not confirmed successful."
            }

            Write-Host "Deployment confirmed successful despite transient 502."
        } else {
            if ($deployOutput) {
                $deployOutput | ForEach-Object { Write-Host $_ }
            }
            throw "Azure web app deploy failed."
        }
    } elseif ($deployOutput) {
        $deployOutput | ForEach-Object { Write-Host $_ }
    }
} finally {
    if ($null -ne $previousNativeErrBehavior) {
        $PSNativeCommandUseErrorActionPreference = $previousNativeErrBehavior
    }
}

# Simple health check and version verification on the actual bound host name
$defaultHostName = az webapp show --resource-group $ResourceGroup --name $AppName --query "defaultHostName" -o tsv --only-show-errors
if (-not $defaultHostName) {
    $defaultHostName = "$AppName.azurewebsites.net"
}

$siteUrl = "https://$defaultHostName"
$healthUrl = "$siteUrl/health"
Write-Host "Checking health endpoint: $healthUrl"
try {
    $response = Invoke-WebRequest -Uri $healthUrl -Method Get -TimeoutSec 30 -UseBasicParsing
    if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
        Write-Host "Health check passed: HTTP $($response.StatusCode)"
    } else {
        Write-Warning "Health endpoint returned HTTP $($response.StatusCode)."
    }

    $runtimeVersion = $null
    try {
        $healthPayload = $response.Content | ConvertFrom-Json -ErrorAction Stop
        $runtimeVersion = $healthPayload.app_version
    } catch {
        Write-Warning "Health response is not valid JSON for version verification."
    }

    if ($runtimeVersion) {
        Write-Host "Runtime APP_VERSION: $runtimeVersion"
        if ($runtimeVersion -eq $deployVersion) {
            Write-Host "Version check passed: runtime APP_VERSION matches deployment version."
        } else {
            Write-Warning "Version mismatch: runtime APP_VERSION '$runtimeVersion' differs from deployment version '$deployVersion'."
        }
    } else {
        Write-Warning "Runtime APP_VERSION was not found in /health response."
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

param(
    [string]$ResourceGroup = "nutrifaq-rg",
    [string]$Location = "canadacentral",
    [string]$PlanName = "nutrifaq-plan-cc",
    [string]$AppName = "nutrifaq-bd",
    [string]$Sku = "B1",
    [string]$Runtime = "PYTHON:3.11",
    [string]$ZipPath = "chromadb-central.zip",
    [switch]$ResetServer,
    [switch]$KeepArtifact
)

$ErrorActionPreference = "Stop"

function Import-DotEnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return @{}
    }

    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#")) {
            continue
        }

        $separatorIndex = $trimmed.IndexOf("=")
        if ($separatorIndex -lt 1) {
            continue
        }

        $name = $trimmed.Substring(0, $separatorIndex).Trim()
        $value = $trimmed.Substring($separatorIndex + 1)
        if (-not [string]::IsNullOrWhiteSpace($name)) {
            $values[$name] = $value
        }
    }

    return $values
}

$dotEnvPath = Join-Path $PSScriptRoot ".env"
$dotEnvValues = Import-DotEnvFile -Path $dotEnvPath

function Get-SettingValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $envItem = Get-Item "Env:$Name" -ErrorAction SilentlyContinue
    if ($envItem -and -not [string]::IsNullOrWhiteSpace($envItem.Value)) {
        return $envItem.Value
    }

    if ($dotEnvValues.ContainsKey($Name) -and -not [string]::IsNullOrWhiteSpace($dotEnvValues[$Name])) {
        return $dotEnvValues[$Name]
    }

    return $null
}

Write-Host "== ChromaDB Central API Azure Deployment =="
Write-Host "Target App Service: $AppName"
Write-Host "Resource Group: $ResourceGroup"
Write-Host "Loading optional settings from: $dotEnvPath"

# Ensure Azure CLI is installed
$azCmd = Get-Command az -ErrorAction SilentlyContinue
if (-not $azCmd) {
    throw "Azure CLI (az) is not installed or not on PATH. Install it first."
}

# Ensure resource group exists
Write-Host "`nEnsuring resource group '$ResourceGroup' exists..."
$rgExists = az group exists --name $ResourceGroup --only-show-errors
if ($rgExists -eq "false") {
    Write-Host "Creating resource group '$ResourceGroup' in '$Location'..."
    az group create --name $ResourceGroup --location $Location | Out-Null
} else {
    Write-Host "Resource group '$ResourceGroup' already exists."
}

# Ensure App Service plan exists
Write-Host "Ensuring App Service plan '$PlanName' exists..."
$planExists = az appservice plan list --resource-group $ResourceGroup --query "[?name=='$PlanName'] | length(@)" -o tsv
if ($planExists -eq "0") {
    Write-Host "Creating App Service plan..."
    az appservice plan create --name $PlanName --resource-group $ResourceGroup --location $Location --sku $Sku --is-linux | Out-Null
}

# Reuse an existing app, otherwise create it
Write-Host "Ensuring web app '$AppName' exists..."
$showCmd = 'az webapp show --resource-group "{0}" --name "{1}" --query "name" -o tsv --only-show-errors' -f $ResourceGroup, $AppName
$appExists = cmd /d /c "$showCmd 2>NUL"
if ($LASTEXITCODE -ne 0) {
    $appExists = ""
}

if ($appExists -and $ResetServer) {
    Write-Host "ResetServer requested; deleting existing web app '$AppName' so deployment starts clean..."
    az webapp delete --resource-group $ResourceGroup --name $AppName --only-show-errors | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to delete Azure web app '$AppName'."
    }

    $appExists = ""
}

if (-not $appExists) {
    Write-Host "Creating web app '$AppName'..."
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

# App settings for the API
Write-Host "`nSetting app configuration..."
$deployVersion = "az-$(Get-Date -Format yyyyMMdd-HHmmss)"
$settingsMap = [ordered]@{
    WEBSITES_PORT = "2000"
    PORT = "2000"
    APP_VERSION = $deployVersion
    WEBSITES_CONTAINER_START_TIME_LIMIT = "1800"
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
    ENABLE_ORYX_BUILD = "true"
    PIP_ROOT_USER_ACTION = "ignore"
}

# Add PostgreSQL and Blob settings if configured locally (optional)
foreach ($settingName in @("POSTGRES_HOST", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_PORT", "POSTGRES_SSLMODE", "POSTGRES_DATABASE_URL", "DATABASE_URL", "AZURE_STORAGE_ACCOUNT", "AZURE_STORAGE_CONTAINER", "AZURE_STORAGE_KEY", "AZURE_BLOB_CONTAINER")) {
    $settingValue = Get-SettingValue -Name $settingName
    if ($settingValue) {
        $settingsMap[$settingName] = $settingValue
    }
}

if (-not $settingsMap.Contains("POSTGRES_HOST") -and -not $settingsMap.Contains("POSTGRES_DATABASE_URL") -and -not $settingsMap.Contains("DATABASE_URL")) {
    Write-Warning "No PostgreSQL connection settings were found in the current session or in $dotEnvPath. The deployed API will keep returning not_configured for SQL health."
}

if (-not $settingsMap.Contains("AZURE_STORAGE_ACCOUNT") -and -not $settingsMap.Contains("AZURE_STORAGE_CONTAINER") -and -not $settingsMap.Contains("AZURE_BLOB_CONTAINER")) {
    Write-Warning "No Azure Blob storage settings were found in the current session or in $dotEnvPath. Blob-backed migration fallback will not be available."
}

Write-Host "PostgreSQL settings to deploy:"
foreach ($settingName in @("POSTGRES_HOST", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_PORT", "POSTGRES_SSLMODE", "POSTGRES_DATABASE_URL", "DATABASE_URL", "AZURE_STORAGE_ACCOUNT", "AZURE_STORAGE_CONTAINER", "AZURE_BLOB_CONTAINER", "AZURE_STORAGE_KEY")) {
    if ($settingsMap.Contains($settingName)) {
        if ($settingName -eq "POSTGRES_PASSWORD" -or $settingName -eq "AZURE_STORAGE_KEY") {
            Write-Host "  - $settingName = <set>"
        } else {
            Write-Host "  - $settingName = $($settingsMap[$settingName])"
        }
    } else {
        Write-Host "  - $settingName = <missing>"
    }
}

$settingsArgs = $settingsMap.GetEnumerator() | ForEach-Object {
    "{0}={1}" -f $_.Key, $_.Value
}
az webapp config appsettings set --resource-group $ResourceGroup --name $AppName --settings $settingsArgs | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure app settings."
}

# Ensure any previously configured run-from-package setting is removed.
az webapp config appsettings delete --resource-group $ResourceGroup --name $AppName --setting-names WEBSITE_RUN_FROM_PACKAGE | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Unable to delete WEBSITE_RUN_FROM_PACKAGE. If it remains set, the app may skip the normal Python build path."
}

Write-Host "Verifying app settings were applied..."
$verifiedSettings = az webapp config appsettings list --resource-group $ResourceGroup --name $AppName --query "[?name=='POSTGRES_HOST' || name=='POSTGRES_USER' || name=='POSTGRES_DB' || name=='POSTGRES_PORT' || name=='POSTGRES_SSLMODE' || name=='POSTGRES_PASSWORD' || name=='POSTGRES_DATABASE_URL' || name=='DATABASE_URL' || name=='AZURE_STORAGE_ACCOUNT' || name=='AZURE_STORAGE_CONTAINER' || name=='AZURE_BLOB_CONTAINER' || name=='AZURE_STORAGE_KEY' || name=='WEBSITE_RUN_FROM_PACKAGE'].{name:name,slotSetting:slotSetting}" -o json
if ($LASTEXITCODE -eq 0 -and $verifiedSettings) {
    $verifiedSettings | ConvertFrom-Json | ForEach-Object {
        Write-Host ("  - {0} (slotSetting={1})" -f $_.name, $_.slotSetting)
    }
} else {
    Write-Warning "Unable to verify app settings from Azure CLI output."
}

# Use a small bootstrap launcher that installs dependencies before loading the app.
Write-Host "Configuring bootstrap startup command..."
$startupCmd = "python /home/site/wwwroot/startup.py"
az webapp config set --resource-group $ResourceGroup --name $AppName --startup-file $startupCmd | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure startup command."
}

# Build zip artifact
$zipBaseName = [System.IO.Path]::GetFileNameWithoutExtension($ZipPath)
$zipDir = [System.IO.Path]::GetDirectoryName($ZipPath)
if ([string]::IsNullOrWhiteSpace($zipDir)) {
    $zipDir = (Get-Location).Path
}
$zipArtifact = Join-Path $zipDir ("{0}-{1}.zip" -f $zipBaseName, (Get-Date -Format "yyyyMMdd-HHmmss"))

Write-Host "`nPackaging ChromaDB Central API into '$zipArtifact'..."

$pythonExe = if (Test-Path -LiteralPath "$PSScriptRoot\.venv\Scripts\python.exe") {
    "$PSScriptRoot\.venv\Scripts\python.exe"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    (Get-Command python).Source
} else {
    throw "Python could not be found. Install Python 3.11 or use the project's virtual environment."
}

$env:ZIP_PATH = $zipArtifact
$env:PROJECT_ROOT = $PSScriptRoot
$tempScript = Join-Path $env:TEMP "create_chromadb_central_zip.py"
@'
import os
import zipfile
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"]).resolve()
zip_path = Path(os.environ["ZIP_PATH"])

# Files needed at runtime.
include_files = [
    "app.py",
    "startup.py",
    "requirements.txt",
    "api/graph_layer.py",
    "api/orchestrator.py",
    "api/postgres_db.py",
    "api/query_chromadb.py",
    "api/migrate_to_postgres.py",
    "api/utils.py",
    "api/routes/__init__.py",
    "api/routes/query.py",
    "api/routes/update.py",
    "api/routes/datasets.py",
    "api/routes/migration.py",
]

with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for relative_path in include_files:
        path = root / relative_path
        if path.is_file():
            zf.write(path, arcname=relative_path)
'@ | Set-Content -Path $tempScript -Encoding UTF8

Write-Host "Creating deployment package..."
& $pythonExe $tempScript
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create the deployment zip package."
}

Write-Host "Package size: $(([System.IO.FileInfo]$zipArtifact).Length / 1MB) MB"

# Deploy zip
Write-Host "`nDeploying to Azure App Service '$AppName'..."
$previousNativeErrBehavior = $null
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $previousNativeErrBehavior = $PSNativeCommandUseErrorActionPreference
    $PSNativeCommandUseErrorActionPreference = $false
}

try {
    $deployOutput = az webapp deployment source config-zip --resource-group $ResourceGroup --name $AppName --src $zipArtifact --only-show-errors 2>&1
    $deployText = ($deployOutput | Out-String)

    if ($LASTEXITCODE -ne 0) {
        if ($deployText -match "Status Code:\s*502") {
            Write-Warning "Azure returned transient 502. Verifying deployment status..."

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
                throw "Deployment failed after 502 error."
            }

            Write-Host "Deployment confirmed successful."
        } else {
            if ($deployOutput) {
                $deployOutput | ForEach-Object { Write-Host $_ }
            }
            throw "Azure webapp deployment failed."
        }
    } else {
        Write-Host "Deployment command completed successfully."
    }
} finally {
    if ($previousNativeErrBehavior -ne $null) {
        $PSNativeCommandUseErrorActionPreference = $previousNativeErrBehavior
    }
}

# Restart the app
Write-Host "`nRestarting app service..."
az webapp restart --resource-group $ResourceGroup --name $AppName | Out-Null

# Test the endpoint
Write-Host "`nTesting ChromaDB Central API..."
$appUrl = "https://$AppName.azurewebsites.net"
$maxRetries = 10
$retryCount = 0

do {
    Start-Sleep -Seconds 2
    $retryCount++
    try {
        $response = Invoke-WebRequest -Uri "$appUrl/health" -Method GET -UseBasicParsing
        Write-Host "[OK] Health check passed: $($response.StatusCode)"
        Write-Host "[OK] Response: $($response.Content)"
        break
    } catch {
        if ($retryCount -lt $maxRetries) {
            Write-Host "[INFO] Waiting for app startup... (attempt $retryCount/$maxRetries)"
        } else {
            Write-Warning "App did not respond after $maxRetries attempts. Check Azure Portal logs for details."
        }
    }
} while ($retryCount -lt $maxRetries)

# Cleanup
if (-not $KeepArtifact) {
    Write-Host "`nCleaning up deployment artifact..."
    Remove-Item -LiteralPath $zipArtifact -Force -ErrorAction SilentlyContinue
}

Write-Host "`n== Deployment Complete =="
Write-Host "App URL: $appUrl"
Write-Host "API Docs: $appUrl/docs"
Write-Host "Health Check: $appUrl/health"
Write-Host ""
Write-Host "API Endpoints:"
Write-Host "  GET  /                    - Status"
Write-Host "  GET  /health              - Health check with DB status"
Write-Host "  POST /query               - Vector query"
Write-Host "  GET  /migration/status    - Migration status"
Write-Host "  GET  /migration/projects  - Available projects"
Write-Host "  POST /migration/migrate-all - Start full migration"
Write-Host ""

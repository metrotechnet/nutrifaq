param(
    [string]$ResourceGroup = "nutrifaq-rg",
    [string]$Location = "canadacentral",
    [string]$PlanName = "nutrifaq-plan-cc",
    [string]$AppName = "nutrifaq-webapp",
    [string]$Sku = "P0v3",
    [string]$Runtime = "PYTHON:3.11",
    [string]$ZipPath = "app.zip",
    [switch]$ResetServer,
    [switch]$ForceClearWwwroot,
    [switch]$KeepArtifact
)

$ErrorActionPreference = "Stop"

Write-Host "== NutriFAQ Azure deployment =="

function Get-DotEnvMap {
    param([string]$Path)

    $map = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $map
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#")) {
            continue
        }

        $sep = $trimmed.IndexOf("=")
        if ($sep -le 0) {
            continue
        }

        $key = $trimmed.Substring(0, $sep).Trim()
        $value = $trimmed.Substring($sep + 1)
        if ($key) {
            $map[$key] = $value
        }
    }

    return $map
}

function Get-AppSettingValue {
    param(
        [string]$Key,
        [hashtable]$DotEnvMap
    )

    $processValue = [Environment]::GetEnvironmentVariable($Key)
    if (-not [string]::IsNullOrWhiteSpace($processValue)) {
        return $processValue
    }

    if ($DotEnvMap.ContainsKey($Key) -and -not [string]::IsNullOrWhiteSpace($DotEnvMap[$Key])) {
        return $DotEnvMap[$Key]
    }

    return $null
}

function Clear-WwwrootViaZipDeploy {
    param(
        [string]$ResourceGroup,
        [string]$AppName
    )

    Write-Warning "Force clear enabled: running a clean deploy with a minimal zip to reset /home/site/wwwroot."

    $tempClearRoot = Join-Path $env:TEMP ("nutrifaq-clear-" + [Guid]::NewGuid().ToString("N"))
    $tempClearZip = Join-Path $env:TEMP ("nutrifaq-clear-" + [Guid]::NewGuid().ToString("N") + ".zip")
    try {
        New-Item -ItemType Directory -Path $tempClearRoot -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $tempClearRoot "clear-marker.txt") -Value "temporary clear package" -Encoding UTF8
        Compress-Archive -Path (Join-Path $tempClearRoot "*") -DestinationPath $tempClearZip -Force

        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $clearZip = [System.IO.Compression.ZipFile]::OpenRead($tempClearZip)
        try {
            $entryCount = $clearZip.Entries.Count
        } finally {
            $clearZip.Dispose()
        }
        if ($entryCount -eq 0) {
            throw "Generated clear zip is empty; aborting clear step."
        }

        az webapp deploy --resource-group $ResourceGroup --name $AppName --src-path $tempClearZip --type zip --clean true --only-show-errors | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Azure empty-zip clean deploy failed while clearing wwwroot."
        }
    } finally {
        if (Test-Path -LiteralPath $tempClearRoot) {
            Remove-Item -LiteralPath $tempClearRoot -Recurse -Force
        }
        if (Test-Path -LiteralPath $tempClearZip) {
            Remove-Item -LiteralPath $tempClearZip -Force
        }
    }

    Write-Host "wwwroot clear step completed via clean deploy."
}

function Show-LatestDeploymentFailureDetails {
    param(
        [string]$ResourceGroup,
        [string]$AppName
    )

    try {
        $deploymentsJson = az webapp log deployment list --resource-group $ResourceGroup --name $AppName -o json --only-show-errors 2>$null
        if (-not $deploymentsJson) {
            Write-Warning "Could not retrieve deployment history for failure diagnostics."
            return
        }

        $deployments = $deploymentsJson | ConvertFrom-Json
        if (-not $deployments) {
            Write-Warning "Deployment history is empty; no failure diagnostics available."
            return
        }

        $failedDeployment = @($deployments | Where-Object { $_.status -eq 3 } | Sort-Object { [datetime]$_.received_time } -Descending)[0]
        if (-not $failedDeployment) {
            Write-Warning "No failed deployment found in recent history."
            return
        }

        $deploymentId = "$($failedDeployment.id)"
        Write-Warning "Latest failed deployment id: $deploymentId"

        $detailsJson = az webapp log deployment show --resource-group $ResourceGroup --name $AppName --deployment-id $deploymentId -o json --only-show-errors 2>$null
        if ($detailsJson) {
            Write-Host "=== Deployment failure details (latest failed id) ==="
            Write-Host $detailsJson
        } else {
            Write-Warning "Could not retrieve detailed logs for deployment id $deploymentId."
        }
    } catch {
        Write-Warning "Failed to fetch deployment diagnostics: $($_.Exception.Message)"
    }
}

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

# Reuse an existing app in the current subscription, otherwise create it.
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
    $createCmd = 'az webapp create --resource-group "{0}" --plan "{1}" --name "{2}" --runtime "{3}" --only-show-errors' -f $ResourceGroup, $PlanName, $AppName, $Runtime
    $createOutput = cmd /d /c "$createCmd 2>&1"
    if ($createOutput) {
        $createOutput | ForEach-Object { Write-Host $_ }
    }

    if ($LASTEXITCODE -ne 0) {
        $errorText = ($createOutput | Out-String)
        if ($errorText -match "globally unique|current subscription|Unable to retrieve details of the existing app") {
            throw "The app name '$AppName' is already in use elsewhere in Azure. Choose a globally unique name with -AppName, for example: -AppName 'nutrifaq-api-$(Get-Date -Format yyyyMMdd)'"
        }
        throw "Failed to create Azure web app '$AppName'."
    }
} else {
    Write-Host "Web app '$AppName' already exists in the current subscription; reusing it."
}

# Minimal app settings
Write-Host "Setting basic app settings..."
$deployVersion = "az-$(Get-Date -Format yyyyMMdd-HHmmss)"
$dotEnvPath = Join-Path $PSScriptRoot ".env"
$dotEnvMap = Get-DotEnvMap -Path $dotEnvPath

$settingsMap = [ordered]@{
    WEBSITES_PORT = "8000"
    PORT = "8000"
    APP_VERSION = $deployVersion
    WEBSITES_CONTAINER_START_TIME_LIMIT = "1800"
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
    ENABLE_ORYX_BUILD = "true"
    PIP_ROOT_USER_ACTION = "ignore"
}

$optionalSettingKeys = @(
    "OPENAI_API_KEY",
    "AI_GATEWAY_API_KEY",
    "LLM_PROVIDER",
    "EMBEDDING_PROVIDER",
    "CHAT_MAX_RETRIES",
    "CHAT_RETRY_BASE_DELAY",
    "CHAT_RETRY_MAX_DELAY",
    "LLM_RETRY_VERBOSE",
    "EMBEDDING_MAX_RETRIES",
    "EMBEDDING_RETRY_BASE_DELAY",
    "EMBEDDING_RETRY_MAX_DELAY",
    "EMBEDDING_SPLIT_AFTER_RETRIES",
    "AZURE_OPENAI_CHAT_ENDPOINT",
    "AZURE_OPENAI_CHAT_API_KEY",
    "AZURE_OPENAI_CHAT_DEPLOYMENT",
    "AZURE_OPENAI_EMBEDDING_ENDPOINT",
    "AZURE_OPENAI_EMBEDDING_API_KEY",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    "ADMIN_ACCESS_KEY",
    "AZURE_STORAGE_CONNECTION_STRING",
    "AZURE_STORAGE_ACCOUNT",
    "AZURE_STORAGE_KEY",
    "AZURE_STORAGE_CONTAINER",
    "AZURE_KB_BLOB_CONTAINER",
    "AZURE_KB_BLOB_PREFIX",
    "ADDITIONAL_CORS_ORIGINS",
    "ADDITIONAL_CORS_ORIGIN_REGEX",
    "ENTRA_TENANT_ID",
    "ENTRA_CLIENT_ID",
    "ENTRA_AUDIENCE",
    "ENTRA_OPENID_CONFIG_URL",
    "DEMO_MODE"
)

$injectedKeys = @()
foreach ($key in $optionalSettingKeys) {
    $value = Get-AppSettingValue -Key $key -DotEnvMap $dotEnvMap
    if ($null -ne $value) {
        $settingsMap[$key] = $value
        $injectedKeys += $key
    }
}

if ($injectedKeys.Count -gt 0) {
    Write-Host "Including optional app settings from environment/.env:" ($injectedKeys -join ", ")
} else {
    Write-Host "No optional app settings found in process environment or .env."
}

$settingsArgs = $settingsMap.GetEnumerator() | ForEach-Object {
    "{0}={1}" -f $_.Key, $_.Value
}
az webapp config appsettings set --resource-group $ResourceGroup --name $AppName --settings $settingsArgs | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure basic Azure app settings."
}

# Ensure the runtime environment has the backend dependencies before each startup.
# App Service on Linux sometimes ignores the inline command when Oryx regenerates startup.sh,
# so we set the startup script file itself and make it install deps before launching the app.
# Also keep the container alive and enable Azure's health probe to prevent the Kudu container
# from being torn down after a brief idle period.
Write-Host "Setting startup file and App Service health settings..."
$startupShPath = Join-Path $PSScriptRoot "startup.sh"
if (-not (Test-Path -LiteralPath $startupShPath)) {
    throw "Missing startup.sh at '$startupShPath'."
}

# The remote Linux container will execute this command itself; do not invoke bash locally.
# Use bash explicitly because the file is a shell script and some App Service Linux images are stricter about /bin/sh behavior.
Write-Host "Verifying startup script exists at '$startupShPath'..."
if (-not (Test-Path -LiteralPath $startupShPath)) {
    throw "Startup script not found: '$startupShPath'"
}
az webapp config set --resource-group $ResourceGroup --name $AppName --startup-file "bash /home/site/wwwroot/startup.sh" --always-on true | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure Azure startup file and App Service health settings."
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
include_dirs = {"api"}
exclude = {
    ".git", ".venv", "__pycache__", ".pytest_cache", ".azure", ".vs",
    ".vscode", ".firebase", "node_modules", "public",
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

$zipContents = python -c "import zipfile, os; z = zipfile.ZipFile(os.environ['ZIP_PATH']); print('\n'.join(z.namelist()))" 2>$null
if ($zipContents) {
    Write-Host "Zip content preview:"
    $zipContents | ForEach-Object { Write-Host $_ }
}
if (-not ($zipContents -match "(^|/)startup\.sh$")) {
    throw "Deployment zip does not contain startup.sh. The App Service startup file will not be available."
}

if ($ForceClearWwwroot) {
    Clear-WwwrootViaZipDeploy -ResourceGroup $ResourceGroup -AppName $AppName
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
        if ($deployText -match "Status Code:\s*502|timeout|unexpected error") {
            Write-Warning "Azure deploy returned a transient deployment error. Verifying latest deployment status..."

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
                throw "Azure deployment returned a transient error and could not be confirmed successful."
            }

            Write-Host "Deployment confirmed successful despite transient Azure error."
        } else {
            if ($deployOutput) {
                $deployOutput | ForEach-Object { Write-Host $_ }
            }
            Show-LatestDeploymentFailureDetails -ResourceGroup $ResourceGroup -AppName $AppName
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

# Validate deployed files under /home/site/wwwroot through Kudu VFS API
Write-Host "Verifying required files in /home/site/wwwroot..."
try {
    $publishingCredsJson = az webapp deployment list-publishing-credentials --resource-group $ResourceGroup --name $AppName --only-show-errors -o json
    if (-not $publishingCredsJson) {
        throw "Failed to read publishing credentials for Kudu validation."
    }

    $publishingCreds = $publishingCredsJson | ConvertFrom-Json
    $scmUri = ("{0}" -f $publishingCreds.scmUri).TrimEnd('/')
    $kuduUrl = "$scmUri/api/vfs/site/wwwroot/"

    $authPair = "{0}:{1}" -f $publishingCreds.publishingUserName, $publishingCreds.publishingPassword
    $encodedAuth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($authPair))
    $headers = @{ Authorization = "Basic $encodedAuth" }

    $wwwrootEntries = Invoke-RestMethod -Uri $kuduUrl -Headers $headers -Method Get -TimeoutSec 30
    $entryNames = @($wwwrootEntries | ForEach-Object { ("{0}" -f $_.name).TrimEnd('/') })

    $requiredEntries = @("app.py", "__init__.py", "requirements.txt", "startup.sh", "api")
    $missingEntries = @($requiredEntries | Where-Object { $_ -notin $entryNames })

    if ($missingEntries.Count -gt 0) {
        throw "Missing required deployed entries in /home/site/wwwroot: $($missingEntries -join ', ')"
    }

    Write-Host "wwwroot validation passed. Required files and folders are present."
} catch {
    throw "Failed to validate /home/site/wwwroot contents: $($_.Exception.Message)"
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

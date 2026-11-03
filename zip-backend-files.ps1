param(
    [string]$ZipPath = "app.zip",
    [string]$AppName = "",
    [string]$ResourceGroup = "",
    [switch]$SkipAppServiceVersionUpdate
)

$ErrorActionPreference = "Stop"

Write-Host "== NutriFAQ zip-only packaging =="

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

function Resolve-AppNameFromBackendUrl {
    param([string]$BackendUrl)

    if ([string]::IsNullOrWhiteSpace($BackendUrl)) {
        return ""
    }
    try {
        $uri = [Uri]$BackendUrl
    } catch {
        return ""
    }
    return ($uri.Host -replace "\.azurewebsites\.net$", "")
}

$projectRoot = $PSScriptRoot
$zipBaseName = [System.IO.Path]::GetFileNameWithoutExtension($ZipPath)
$zipDir = [System.IO.Path]::GetDirectoryName($ZipPath)
if ([string]::IsNullOrWhiteSpace($zipDir)) {
    $zipDir = (Get-Location).Path
}
$packageVersion = "az-$(Get-Date -Format "yyyyMMdd-HHmmss")"
$zipArtifact = Join-Path $zipDir ("{0}-{1}.zip" -f $zipBaseName, (Get-Date -Format "yyyyMMdd-HHmmss"))

Write-Host "Packaging project into '$zipArtifact'..."
Write-Host "Package APP_VERSION: $packageVersion"

$pythonExe = if (Test-Path -LiteralPath "$projectRoot\.venv\Scripts\python.exe") {
    "$projectRoot\.venv\Scripts\python.exe"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    (Get-Command python).Source
} else {
    throw "Python could not be found. Install Python 3.11 or use the project's virtual environment."
}

$env:ZIP_PATH = $zipArtifact
$env:PROJECT_ROOT = $projectRoot
$env:PACKAGE_VERSION = $packageVersion
$tempScript = Join-Path $env:TEMP "create_azure_zip_only.py"
@'
import os
import re
import zipfile
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"]).resolve()
zip_path = Path(os.environ["ZIP_PATH"])
package_version = os.environ["PACKAGE_VERSION"]
include = {"app.py", "__init__.py", "requirements.txt", "startup.sh"}
include_dirs = {"api", "templates"}
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
                if entry.name == "app.py":
                    app_text = entry.read_text(encoding="utf-8")
                    app_text = re.sub(
                        r'APP_VERSION\s*=\s*os\.getenv\("APP_VERSION",\s*"[^"]*"\)',
                        f'APP_VERSION = os.getenv("APP_VERSION", "{package_version}")',
                        app_text,
                        count=1,
                    )
                    zf.writestr(entry.name, app_text.encode("utf-8"))
                else:
                    zf.write(entry, arcname=entry.name)
'@ | Set-Content -Path $tempScript -Encoding UTF8

& $pythonExe $tempScript
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create zip package."
}

$zipContents = & $pythonExe -c "import zipfile, os; z = zipfile.ZipFile(os.environ['ZIP_PATH']); print('\\n'.join(z.namelist()))"
$zipEntries = @()
if ($zipContents) {
    $zipContentsNormalized = ($zipContents -replace '\\n', "`n")
    $zipEntries = @($zipContentsNormalized -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}
if ($zipContents) {
    Write-Host "Zip content preview:"
    $zipEntries | ForEach-Object { Write-Host $_ }
}
if (-not ($zipEntries -contains "startup.sh")) {
    throw "Zip package does not contain startup.sh."
}

Write-Host "Zip complete: $zipArtifact"

if (-not $SkipAppServiceVersionUpdate) {
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        throw "Azure CLI (az) is required to update APP_VERSION on App Service."
    }

    if ([string]::IsNullOrWhiteSpace($AppName)) {
        $dotEnvMap = Get-DotEnvMap -Path (Join-Path $projectRoot ".env")
        $AppName = Resolve-AppNameFromBackendUrl -BackendUrl ([string]$dotEnvMap["BACKEND_URL"])
    }

    if ([string]::IsNullOrWhiteSpace($AppName)) {
        throw "Unable to resolve App Service name. Pass -AppName explicitly or set BACKEND_URL in .env."
    }

    if ([string]::IsNullOrWhiteSpace($ResourceGroup)) {
        $ResourceGroup = az webapp list --query "[?name=='$AppName'].resourceGroup | [0]" -o tsv --only-show-errors
    }
    if ([string]::IsNullOrWhiteSpace($ResourceGroup)) {
        throw "Unable to resolve resource group for app '$AppName'. Pass -ResourceGroup explicitly."
    }

    Write-Host "Updating App Service APP_VERSION to '$packageVersion' (app='$AppName', rg='$ResourceGroup')..."
    az webapp config appsettings set `
        --resource-group $ResourceGroup `
        --name $AppName `
        --settings "APP_VERSION=$packageVersion" `
        --only-show-errors | Out-Null

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to update APP_VERSION on App Service."
    }
    Write-Host "App Service APP_VERSION updated."
}
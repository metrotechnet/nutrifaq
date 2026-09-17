param(
    [string]$ZipPath = "app.zip"
)

$ErrorActionPreference = "Stop"

Write-Host "== NutriFAQ zip-only packaging =="

$projectRoot = $PSScriptRoot
$zipBaseName = [System.IO.Path]::GetFileNameWithoutExtension($ZipPath)
$zipDir = [System.IO.Path]::GetDirectoryName($ZipPath)
if ([string]::IsNullOrWhiteSpace($zipDir)) {
    $zipDir = (Get-Location).Path
}
$zipArtifact = Join-Path $zipDir ("{0}-{1}.zip" -f $zipBaseName, (Get-Date -Format "yyyyMMdd-HHmmss"))

Write-Host "Packaging project into '$zipArtifact'..."

$pythonExe = if (Test-Path -LiteralPath "$projectRoot\.venv\Scripts\python.exe") {
    "$projectRoot\.venv\Scripts\python.exe"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    (Get-Command python).Source
} else {
    throw "Python could not be found. Install Python 3.11 or use the project's virtual environment."
}

$env:ZIP_PATH = $zipArtifact
$env:PROJECT_ROOT = $projectRoot
$tempScript = Join-Path $env:TEMP "create_azure_zip_only.py"
@'
import os
import zipfile
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"]).resolve()
zip_path = Path(os.environ["ZIP_PATH"])
include = {"app.py", "__init__.py", "requirements.txt", "startup.sh"}
include_dirs = {"api", "knowledge-base"}
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
    throw "Failed to create zip package."
}

$zipContents = & $pythonExe -c "import zipfile, os; z = zipfile.ZipFile(os.environ['ZIP_PATH']); print('\\n'.join(z.namelist()))"
if ($zipContents) {
    Write-Host "Zip content preview:"
    $zipContents | ForEach-Object { Write-Host $_ }
}
if (-not ($zipContents -match "(^|/)startup\.sh$")) {
    throw "Zip package does not contain startup.sh."
}

Write-Host "Zip complete: $zipArtifact"
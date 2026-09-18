param(
    [int]$Port = 5501
)

Write-Host "Starting Example Frontend Server..." -ForegroundColor Green
Write-Host ""

$SCRIPT_DIR = $PSScriptRoot
$EXAMPLE_DIR = Join-Path $SCRIPT_DIR "example\simple-frontend-chat"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Starting Example Frontend Server (Python http.server)..." -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $EXAMPLE_DIR)) {
    Write-Host "Error: Example folder not found at $EXAMPLE_DIR" -ForegroundColor Red
    exit 1
}

# Prefer project virtualenv Python, fallback to system Python.
$PYTHON_PATH = Join-Path $SCRIPT_DIR ".venv\Scripts\python.exe"
if (Test-Path $PYTHON_PATH) {
    Write-Host "Using Python from virtual environment" -ForegroundColor Green
} else {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        Write-Host "Error: Python was not found (neither .venv nor PATH)." -ForegroundColor Red
        exit 1
    }
    $PYTHON_PATH = $pythonCmd.Source
    Write-Host "Using Python from PATH: $PYTHON_PATH" -ForegroundColor Yellow
}

Write-Host "Serving: $EXAMPLE_DIR" -ForegroundColor Cyan
Write-Host "URL: http://127.0.0.1:$Port" -ForegroundColor Cyan
Write-Host ""

Set-Location $EXAMPLE_DIR
& $PYTHON_PATH -m http.server $Port

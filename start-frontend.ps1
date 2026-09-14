# Start IMX Frontend Server with Python (includes env variable templating)
Write-Host "Starting IMX Frontend Server..." -ForegroundColor Green
Write-Host ""

$SCRIPT_DIR = $PSScriptRoot

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Starting Frontend Server (Python with env templating)..." -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# Run the Python frontend server using the venv Python directly
$PYTHON_PATH = Join-Path $SCRIPT_DIR ".venv\Scripts\python.exe"

if (-not (Test-Path $PYTHON_PATH)) {
    Write-Host "Error: Virtual environment not found at $PYTHON_PATH" -ForegroundColor Red
    Write-Host "Run this first: python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

Write-Host "Using Python from virtual environment" -ForegroundColor Green
Write-Host ""

# Run the Python frontend server
& $PYTHON_PATH serve_frontend.py

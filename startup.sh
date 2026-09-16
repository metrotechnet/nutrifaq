#!/bin/bash
set -e

cd /home/site/wwwroot

echo "Installing Python dependencies..."
python -m pip install --no-cache-dir -r /home/site/wwwroot/requirements.txt

echo "Starting uvicorn server on port ${PORT:-8000}..."
exec python /home/site/wwwroot/app.py

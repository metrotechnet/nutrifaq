#!/bin/bash
set -e

echo "Starting uvicorn server on port ${PORT:-8080}..."
exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080} --workers 2 --timeout-keep-alive 300

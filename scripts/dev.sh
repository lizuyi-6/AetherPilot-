#!/usr/bin/env bash
# Start backend (:8000) and frontend (:5173) together.
set -euo pipefail
cd "$(dirname "$0")/.."

.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT

cd frontend && npm run dev

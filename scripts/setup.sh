#!/usr/bin/env bash
# AetherPilot setup: backend venv + deps, frontend deps.
set -euo pipefail
cd "$(dirname "$0")/.."

if command -v uv >/dev/null 2>&1; then
  uv venv .venv
  uv pip install --python .venv/bin/python -r backend/requirements.txt
else
  python3 -m venv .venv
  .venv/bin/python -m pip install -r backend/requirements.txt
fi

cd frontend && npm install
echo "Setup complete. Run: scripts/dev.sh"

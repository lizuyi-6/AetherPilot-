#!/usr/bin/env bash
# Run the full demo scenario (OOM + NaN, two autonomous recoveries) against a
# running backend, printing the state machine as it progresses.
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python backend/tests/e2e_smoke.py

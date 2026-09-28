# AetherPilot setup (Windows): backend venv + deps, frontend deps.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (Get-Command uv -ErrorAction SilentlyContinue) {
  uv venv .venv
  uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt
} else {
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r backend\requirements.txt
}

Push-Location frontend
npm install
Pop-Location
Write-Host "Setup complete. Run: scripts\dev.ps1"

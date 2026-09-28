# Start backend (:8000) and frontend (:5173). Ctrl+C stops both.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$backend = Start-Process -PassThru -NoNewWindow `
  -FilePath ".venv\Scripts\python.exe" `
  -ArgumentList "-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--app-dir","backend"
try {
  Push-Location frontend
  npm run dev
} finally {
  Pop-Location
  if (!$backend.HasExited) { $backend.Kill() }
}

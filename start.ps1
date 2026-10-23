# Starts RunbookPilot: backend API (port 8000) and web app (port 5173), each in its own window.
# Docker Desktop must be running for sandbox tests.
$root = $PSScriptRoot
Start-Process powershell -ArgumentList '-NoExit', '-Command', "cd '$root\backend'; .\.venv\Scripts\python -m uvicorn app.main:app --port 8000 --reload"
Start-Process powershell -ArgumentList '-NoExit', '-Command', "cd '$root\frontend'; npm run dev"
Start-Sleep -Seconds 4
Start-Process 'http://localhost:5173'

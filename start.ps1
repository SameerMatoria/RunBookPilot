# Starts RunbookPilot for local development: Postgres (Docker), then the API (port 8000), a worker,
# and the web app (port 5173), each in its own window. Docker Desktop must be running.
$root = $PSScriptRoot

docker compose -f "$root\docker-compose.yml" up -d db
if (-not $?) { Write-Host "Could not start Postgres. Is Docker Desktop running?" -ForegroundColor Red; exit 1 }

# Bring the database schema up to date before anything uses it.
Push-Location "$root\backend"
.\.venv\Scripts\alembic upgrade head
Pop-Location

Start-Process powershell -ArgumentList '-NoExit', '-Command', "cd '$root\backend'; .\.venv\Scripts\python -m uvicorn app.main:app --port 8000 --reload"
Start-Process powershell -ArgumentList '-NoExit', '-Command', "cd '$root\backend'; .\.venv\Scripts\python -m app.worker"
Start-Process powershell -ArgumentList '-NoExit', '-Command', "cd '$root\frontend'; npm run dev"
Start-Sleep -Seconds 4
Start-Process 'http://localhost:5173'

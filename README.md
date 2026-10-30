# RunbookPilot

Turns written IT runbooks into tested, approved automation. Upload a runbook; four AI agents
extract the steps, write a Bash script, test it in a disposable Docker sandbox (fixing it up to 3
times), and write a summary card. An engineer (not the uploader) approves it, and operators can then
run it on real servers over SSH: by hand, on a schedule, or from a monitoring alert.

See [RunbookPilot-Blueprint.html](RunbookPilot-Blueprint.html) for the original plan,
[ARCHITECTURE.html](ARCHITECTURE.html) for how it works, and [ROADMAP.md](ROADMAP.md) for what's next.

## Run it

Prerequisites: Python 3.12, Node 20+, Docker Desktop (running), a free Groq API key.
Step-by-step instructions for a new machine: [SETUP.html](SETUP.html).

### Option A: everything in Docker

```powershell
copy backend\.env.example backend\.env      # then paste your API key into backend\.env
docker compose up -d --build                # http://localhost:8080
```

### Option B: local development (hot reload)

```powershell
# one-time setup
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env          # then paste your API key into .env
cd ..\frontend
npm install
cd ..

# every time
.\start.ps1     # starts Postgres (Docker), applies migrations, then the API, a worker and the web app
```

The sandbox image builds automatically the first time a script is tested (about 1 minute), and
rebuilds by itself whenever the files in `sandbox/` change.

### First sign-in

On a fresh database the sign-in page offers **Create the first admin**. That admin then adds
everyone else on the **Users** page (or from the command line:
`python -m app.users_cli create <username> --roles approver,operator`).

| Role | Can |
|---|---|
| submitter | upload runbooks, answer the agents' questions, retry |
| approver | approve, request changes to, or reject scripts (never their own uploads; high-risk needs two approvers) |
| operator | run approved scripts on servers, manage schedules and alert triggers |
| admin | everything, plus users, servers, credentials and the audit log |

**Microsoft Entra ID sign-in (optional):** register an app in Entra ID (single-page application,
redirect URI = the web app's address), then set `ENTRA_TENANT_ID` and `ENTRA_CLIENT_ID` in
`backend/.env`. New Microsoft users get `ENTRA_DEFAULT_ROLES`; if the app registration defines app
roles named Submitter/Approver/Operator/Admin, those are synced on every sign-in.

### Running scripts on servers

1. **Servers** page (admin): add a credential (SSH key or password; encrypted, never shown again),
   then a server, then **Test connection**. The first successful test pins the server's SSH host key;
   later connections to a server presenting a different key are refused.
2. On an approved runbook, the **Run on servers** panel (operator): pick servers, dry run or execute
   (execute always does a dry run first), plus a change ticket (required for high-risk scripts).
3. Every run is on the **Runs** page with live output and per-step results, and in the audit log.

**Demo server:** `docker compose up -d demo-server` starts a pretend server with SSH (user `ops`,
password `runbookpilot-demo`; demo only, bound to localhost). Add it as hostname `demo-server`,
port 22 when using the Docker stack, or `localhost`, port 2222 when the worker runs via `start.ps1`.

### Tests

```powershell
cd backend
.venv\Scripts\python -m pytest       # fast, no AI calls or Docker needed (SQLite + fakes)
```

CI (GitHub Actions) runs the tests on SQLite and on Postgres, checks the migrations, builds the web
app and builds all Docker images.

## Benchmark: the 10 sample runbooks

`samples/` holds 10 runbooks: service restarts, disk cleanup, certificate checks, diagnostics,
health checks, cache clearing, permissions, user onboarding, a config change and crash recovery.
Run them all through the pipeline, answering the agents' questions from
`samples/engineer-answers.json` (needs Postgres running):

```powershell
cd backend
.venv\Scripts\python run_benchmark.py                      # all 10 (about 20 minutes)
.venv\Scripts\python run_benchmark.py clear-app-cache.md   # just one
```

Results appear on the **Impact** page of the web app. Nothing is approved automatically.
The manual times and frequencies in the sample runbooks are estimates; replace them with real
numbers from your team before quoting the ROI.

**Free AI quotas:** Groq's free tier allows about 200,000 tokens a day per model, roughly 10
runbook conversions. `LLM_FALLBACK_MODELS` chains more models (each has its own quota), and a
Gemini key in `LLM_FALLBACK_*` adds a separate provider.

## How it fits together

| Piece | File | Azure in production |
|---|---|---|
| Parser, Author, Tester, Reviewer agents | `backend/app/agents/` | Foundry Agent Service |
| Test-and-fix loop | `backend/app/pipeline.py` | |
| Lint gate (blocked commands + ShellCheck) | `backend/app/lint.py` | |
| Sandbox (Debian + nginx + myapp, seeded server state) | `backend/app/sandbox.py`, `sandbox/` | Container Apps Jobs |
| AI model chain (any OpenAI-compatible API) | `backend/app/llm.py` | Azure AI Foundry |
| API | `backend/app/main.py` | Container Apps |
| Job queue (in Postgres) and worker | `backend/app/jobqueue.py`, `backend/app/worker.py` | Container Apps |
| Database and migrations | `backend/app/models.py`, `backend/migrations/` | Postgres Flexible Server |
| Sign-in, roles, audit log | `backend/app/auth.py`, `backend/app/audit.py`, `backend/app/routes/` | Entra ID |
| Servers, encrypted credentials | `backend/app/routes/servers.py`, `backend/app/secrets_store.py` | Key Vault |
| SSH runs, schedules, alert webhooks | `backend/app/executor.py`, `backend/app/ssh.py`, `backend/app/runs.py` | Azure Automation (optional) |
| Impact metrics (projected and measured) | `backend/app/metrics.py`, `frontend/src/components/Dashboard.jsx` | |
| Web app | `frontend/` (React + Vite) | Static Web Apps |

## API

All endpoints except `/health`, sign-in and `/hooks/*` need a signed-in user (session cookie, or
`Authorization: Bearer <token>` from `/auth/login`). Interactive docs: `/docs` on the API.

- `POST /runbooks` upload (multipart `file`), queues the Parser
- `GET /runbooks`, `GET /runbooks/{id}` status, steps, scripts, test runs, review, live events
- `POST /runbooks/{id}/answers` `{"answers": {"3": "..."}}`; queues the build once all are answered
- `POST /runbooks/{id}/build` `{"feedback": "..."}` write, test and review (alias `/regenerate`)
- `POST /runbooks/{id}/retry` after an error, continue from where it stopped
- `POST /runbooks/{id}/approve` `{"comment": "..."}`; high risk needs 2 approvers
- `POST /runbooks/{id}/request-changes` `{"comment": "..."}` the comment goes to the Author; the new version is tested and reviewed again
- `POST /runbooks/{id}/reject` `{"comment": "..."}` final: nothing is rebuilt
- `DELETE /runbooks/{id}`
- `POST /auth/login`, `/auth/entra`, `/auth/setup`, `/auth/logout`; `GET /auth/me`, `/auth/config`
- `GET/POST /users`, `PATCH /users/{id}`, `GET /audit` (admin)
- `GET/POST /credentials`, `DELETE /credentials/{id}`; `GET/POST /servers`, `PATCH/DELETE /servers/{id}`, `POST /servers/{id}/test`
- `POST /runbooks/{id}/runs` `{"server_ids": [..], "mode": "dry_run"|"execute", "ticket": ".."}`; `GET /runs`, `GET /runs/{id}`, `POST /runs/{id}/cancel`
- `GET/POST /runbooks/{id}/schedules` (cron, UTC), `PATCH/DELETE /schedules/{id}`
- `GET/POST /runbooks/{id}/triggers`, `DELETE /triggers/{id}`; monitoring calls `POST /hooks/{id}` with header `X-RunbookPilot-Token`
- `GET /metrics` conversion rate, time to automate, hours saved (projected and measured)
- `GET /health`; `GET /sandbox` (reported by the workers' heartbeats)

Agent work is queued for the worker. Add `?wait=true` to run it inline and wait for the result.

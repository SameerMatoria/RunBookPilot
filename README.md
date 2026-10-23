# RunbookPilot

Turns written IT runbooks into tested, approved automation. Upload a runbook; four AI agents
extract the steps, write a Bash script, test it in a disposable Docker sandbox (fixing it up to 3
times), and write a summary card. Nothing is "live" until an engineer approves it.

See [RunbookPilot-Blueprint.html](RunbookPilot-Blueprint.html) for the full plan.

## Run it

Prerequisites: Python 3.12, Node 20+, Docker Desktop (running), a free Groq API key.

```powershell
# one-time setup
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env          # then paste your API key into .env
cd ..\frontend
npm install
cd ..

# every time
.\start.ps1                     # opens http://localhost:5173
```

The sandbox image builds automatically the first time a script is tested (about 1 minute).

Command-line check of the whole flow, no UI needed:
`cd backend; .venv\Scripts\python try_pipeline.py ..\samples\restart-web-service.md`

## How it fits together

| Piece | File | Blueprint equivalent |
|---|---|---|
| Parser agent | `backend/app/agents/parser.py` | Parser agent |
| Author agent | `backend/app/agents/author.py` | Author agent |
| Tester agent + fix loop | `backend/app/agents/tester.py`, `pipeline.py` | Tester agent |
| Reviewer agent | `backend/app/agents/reviewer.py` | Reviewer agent |
| Lint gate (blocked commands + ShellCheck) | `backend/app/lint.py` | Lint gates |
| Sandbox | `backend/app/sandbox.py`, `sandbox/` | Container Apps jobs |
| AI model | `backend/app/llm.py` (any OpenAI-compatible API) | Foundry model |
| Storage | `backend/app/store.py` (JSON files in `data/`) | Cosmos DB |
| Web app | `frontend/` (React + Vite) | Static Web Apps |

Moving to Azure later means swapping these one at a time; the AI provider is just the `LLM_*`
settings in `backend/.env`.

## API

- `POST /runbooks` upload (multipart `file`), starts the Parser
- `GET /runbooks`, `GET /runbooks/{id}` status, steps, scripts, test runs, review, live events
- `POST /runbooks/{id}/answers` `{"answers": {"3": "..."}}`; starts the build once all are answered
- `POST /runbooks/{id}/build` `{"feedback": "..."}` write, test and review (alias `/regenerate`)
- `POST /runbooks/{id}/approve` / `/reject` `{"reviewer": "...", "comment": "..."}`; high risk needs 2 approvers; reject sends the comment back to the Author
- `GET /health`, `GET /sandbox`

Add `?wait=true` to any agent-triggering call to block until it finishes.

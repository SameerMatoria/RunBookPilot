# Trial runbooks

Synthetic runbooks written to look like what operations teams actually keep, rather than tidy
samples written for the sandbox: wiki prose, a plain-text checklist, a Word document, an incident
runbook with branches, and some that need software the sandbox doesn't have (logrotate, Node.js
with pm2, PostgreSQL) or a platform RunbookPilot doesn't support (Windows).

Run them with:

    python run_benchmark.py --set trial

`engineer-answers.json` holds the facts an on-call engineer would give when the Parser asks a
question. Results are in [RESULTS.md](RESULTS.md).

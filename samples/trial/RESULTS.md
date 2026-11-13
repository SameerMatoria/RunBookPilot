# Trial results

Synthetic runbooks written to look like real team documents, run through the full pipeline with
`python run_benchmark.py --set trial`. The Parser's questions were answered from
`engineer-answers.json`. Nothing was approved automatically.

## Summary

| | Round 1 (10 runbooks) | Round 2 (same 10 + 5 new) |
|---|---|---|
| **Tested script, ready for approval** | **1** | **7** |
| Refused as intended (Windows) | 1 | 1 |
| Handed over: needs software or files the sandbox doesn't have | 3 | 5 |
| Handed over: failed for other reasons | 5 | 1 |
| Not finished: AI quota ran out | 0 | 1 |

In round 2, **3 of the 5 new runbooks** became tested scripts. Those runbooks were written after the
fixes, so the fixes weren't tailored to them. No runbook produced an untested script: every
failure was stopped and handed to an engineer.

## Round 2: after the fixes (13 November 2026)

| Runbook | Format | Outcome | Fix attempts |
|---|---|---|---|
| kill-stuck-report-workers | Markdown | ✅ Tested | 0 |
| listening-ports-audit | Markdown | ✅ Tested (was: invented a setting) | 0 |
| myapp-memory-incident | Markdown | ✅ Tested (was: sandbox gap) | 0 |
| tls-expiry-check | Plain text | ✅ Tested (was: sandbox gap) | 0 |
| nginx-5xx-spike *(new)* | Markdown | ✅ Tested | 0 |
| template-cache-cleanup *(new)* | Bullet list | ✅ Tested | 0 |
| pre-patch-snapshot *(new)* | Word | ✅ Tested after 1 fix by the agents | 1 |
| windows-iis-recycle | Markdown | ✅ Refused: Windows isn't supported | |
| db-connection-check | Markdown | ⛔ Needs PostgreSQL | 0 |
| restart-orders-api | Markdown | ⛔ Needs Node.js, pm2 and an `orders` user | 0 |
| rotate-myapp-logs | Markdown | ⛔ Needs logrotate and its config file | 0 |
| rotate-payment-api-key *(new)* | Markdown | ⛔ Needs the app's config file `/etc/myapp/app.env` | 0 |
| schedule-cache-cleanup *(new)* | Plain text | ⛔ Needs a running cron service | 1 |
| nginx-maintenance-mode | Word | ❌ Agents couldn't get the nginx config edit right in 3 fixes | 3 |
| var-filling-up | Wiki prose | ⚠️ Not finished: every AI model hit its free-tier limit | |

**What changed between rounds:**
- **Author:** never demands inputs the runbook doesn't give; manual steps (tickets, sheets, telling
  people) become skipped steps with a note; a "when to use" line is not turned into a check that stops
  the script.
- **Tester:** an input the script invented, or a manual step turned into a required one, is a script
  bug to fix, not an environment problem.
- **Sandbox:** a `journalctl` stand-in, more `systemctl` commands, and a test certificate with a SAN,
  as on a real Debian server.

**What's still missing:**
1. **Runbooks that need software or files the sandbox doesn't have** (5 of 15). They're handed over
   safely, but not automated. This is the roadmap item "sandbox built from what the runbook needs".
2. **Harder config edits** (nginx maintenance mode) can still defeat the fix loop.
3. **Free AI quota:** Groq allows 200,000 tokens a day per model, and this run used it up. The
   backup models have small per-minute limits, and Gemini was overloaded (HTTP 503) at the time, so
   one runbook stopped with an error. It can be retried with the Retry button once the quota resets.

## Round 1: before the fixes (13 November 2026)

**1 of 10 became a tested script.**

| Runbook | Outcome | Cause (checked in the logs) |
|---|---|---|
| kill-stuck-report-workers | ✅ Tested | |
| windows-iis-recycle | ✅ Refused as intended | |
| db-connection-check | ⛔ Handed over | Needs `psql` |
| restart-orders-api | ⛔ Handed over | Needs Node.js and `pm2` |
| rotate-myapp-logs | ⛔ Handed over | Needs `logrotate`; also refused to run unless app.log was over 1 GB |
| var-filling-up | ⛔ Handed over | No `journalctl` in the sandbox |
| myapp-memory-incident | ⛔ Handed over | Stand-in `systemctl` lacked `list-unit-files` |
| tls-expiry-check | ⛔ Handed over | Test certificate had no SAN, so the script correctly reported a failed check |
| listening-ports-audit | ⛔ Handed over | **Bug:** demanded an `AUDIT_SHEET_PATH` setting the runbook never mentions |
| nginx-maintenance-mode | ⛔ Handed over | **Bug:** turned "tell the service desk" into a step demanding `SERVICE_DESK_URL` |

Every failure was handed over without a single fix attempt, because the Tester called each one an
environment problem.

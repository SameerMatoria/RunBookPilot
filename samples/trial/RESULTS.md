# Trial results: 13 November 2026

10 new synthetic runbooks, written to look like real team documents, run once through the full
pipeline (`python run_benchmark.py --set trial`). The Parser's questions were answered from
`engineer-answers.json`. Nothing was approved.

**Result: 1 of 10 became a tested script ready for approval.** That's far below the first set of
samples (10 of 10), which were written to fit the sandbox.

| Runbook | Format | Outcome | Real cause (checked in the logs) |
|---|---|---|---|
| kill-stuck-report-workers | Markdown | ✅ Tested, ready for approval | |
| windows-iis-recycle | Markdown | ✅ Refused as intended | Windows is not supported |
| db-connection-check | Markdown | ⛔ Handed to engineer | Needs `psql`, which the sandbox doesn't have |
| restart-orders-api | Markdown | ⛔ Handed to engineer | Needs Node.js and `pm2`, which the sandbox doesn't have |
| rotate-myapp-logs | Markdown | ⛔ Handed to engineer | Needs `logrotate` (not in the sandbox); the script also refuses to run unless app.log is over 1 GB |
| var-filling-up | Wiki prose | ⛔ Handed to engineer | `journalctl` isn't in the sandbox, though real servers have it |
| myapp-memory-incident | Markdown | ⛔ Handed to engineer | The sandbox's stand-in `systemctl` doesn't support `list-unit-files` |
| tls-expiry-check | Plain text | ⛔ Handed to engineer | The sandbox's test certificate has no SAN, so the script correctly reported a failed check |
| listening-ports-audit | Markdown | ⛔ Handed to engineer | **Our bug:** the script demands an `AUDIT_SHEET_PATH` setting the runbook never mentions |
| nginx-maintenance-mode | Word | ⛔ Handed to engineer | **Our bug:** the manual "tell the service desk" step became a step that demands a `SERVICE_DESK_URL` setting |

Every failure was handed over after the first test, with no fix attempts, because the Tester agent
classed each one as an environment problem rather than a script bug.

## What this tells us

1. **The Author invents required settings** (2 runbooks). A manual step, such as updating a sheet
   or telling the service desk, should become a skipped step with a note, not a demand for a
   setting nobody gave.
2. **The Tester gives up too early** (same 2). A setting the script itself invented is a script
   bug and should be fixed and retested, not handed over as an environment problem.
3. **The sandbox is less realistic than a real server** (3 runbooks): no `journalctl`, a stand-in
   `systemctl` with few commands, and a test certificate without a SAN.
4. **Runbooks that need software the sandbox lacks** (3 runbooks: PostgreSQL, Node.js/pm2,
   logrotate) are handed over, which is the safe outcome. Supporting them is the roadmap item
   "sandbox built from what the runbook needs".
5. **The Parser handled every format**, including wiki prose and a Word document whose step
   numbers were lost in extraction.
6. **Groq's free tier limits tokens per minute** (8,000): 3 agent calls hit it and fell back to
   the backup models, which worked.

Results 1 to 3 can be fixed generally (in the agents' instructions and the sandbox image), not by
tailoring anything to these runbooks. After fixing them, these runbooks should be re-run, together
with a few new ones, because re-running only these would flatter the result.

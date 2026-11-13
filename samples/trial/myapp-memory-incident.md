# Incident runbook: MyApp killed by the OOM killer

**Severity:** P2 (P1 if it happens again within an hour)
**Trigger:** "myapp exited (signal 9)" alert, or the health check on port 8080 failing
**Manual time:** 25 minutes
**Frequency:** about 6 times a month

## Diagnose
1. Confirm the service state: `systemctl status myapp`.
2. Check `/var/log/myapp/error.log` for `OOM killer` or `out of memory`. Note the time of the last one.
3. Check memory on the box: `free -m`. Note available memory.
4. Find the five processes using the most memory.

## Decide
- If there is **no** OOM line in the log, this is not a memory incident: stop here and follow the
  general "MyApp down" runbook instead.
- If available memory is **below 200 MB**, something else is eating memory. Do not restart MyApp;
  escalate to the platform team with the process list from step 4.
- Otherwise continue.

## Recover
5. Restart MyApp.
6. Wait up to 30 seconds for `http://localhost:8080/health` to return 200, checking every 5 seconds.
7. If it never returns 200, escalate to the MyApp team with the last 50 lines of the error log.

## Close
8. Add the OOM time, free memory and outcome to the incident ticket.

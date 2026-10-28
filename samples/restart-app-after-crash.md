# Runbook: Recover MyApp after a crash

**Owner:** Application Support
**When to use:** "myapp down" alert, or users report the app is not responding on port 8080.
**Manual time:** about 20 minutes
**Frequency:** about 18 times a month

Steps:

1. Check if myapp is running and if port 8080 is listening.
2. Look at the end of `/var/log/myapp/error.log` and count how many out-of-memory / OOM lines there are. Copy the last 20 lines into the ticket.
3. Check how much memory is free on the box.
4. Restart myapp.
5. Wait for it to come up, then make sure the health page (port 8080, /health) gives 200. Try a few times before giving up.
6. If it keeps crashing, escalate to the app team with the log lines.
7. Check the nginx front end still works too.

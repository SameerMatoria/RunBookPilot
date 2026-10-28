# Runbook: Collect a diagnostics bundle for escalation

**Owner:** L2 Support
**When to use:** Before escalating an incident to the application vendor or L3.
**Manual time:** about 25 minutes
**Frequency:** about 15 times a month

Vendors always ask for the same information, so gather it in one archive.

## Steps
1. Make a working folder `/tmp/diag-<hostname>-<date>`.
2. Save basic system info: hostname, kernel version (`uname -a`), uptime.
3. Save disk usage (`df -h`) and memory usage (`free -m`).
4. Save the top 15 processes by memory.
5. Save which ports are listening (`ss -ltnp`).
6. Save the status of the nginx and myapp services.
7. Copy the last 200 lines of `/var/log/nginx/error.log` and `/var/log/myapp/error.log`.
8. Pack the folder into `/tmp/diag-<hostname>-<date>.tar.gz` and print its path and size.
9. Attach the archive to the ticket.

Read-only: do not restart anything while collecting.

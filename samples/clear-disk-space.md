# Runbook: Free up disk space on a web server

**Owner:** Platform Ops
**When to use:** "Disk usage high" alert on /var or / for a web server.
**Manual time:** about 20 minutes
**Frequency:** about 25 times a month

## Before you start
Do not delete the current log files (`access.log`, `error.log`) or anything outside /var/log and /tmp.
Note the disk usage before and after in the ticket.

## Steps
1. Record current usage: `df -h /var/log /tmp`
2. Find the biggest items in /var/log: `du -sh /var/log/* | sort -h | tail`
3. Delete compressed nginx logs (`*.gz`) in /var/log/nginx older than 7 days.
4. Delete compressed application logs in /var/log/myapp older than 7 days.
5. Remove stale upload temp files: `/tmp/upload_*.tmp` older than 2 days.
6. Run `df -h /var/log /tmp` again and confirm usage went down (or at least did not go up).
7. Make sure nginx is still running.

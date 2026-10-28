# Runbook: Daily server health check

**Owner:** NOC
**When to use:** Every morning, for each managed web server.
**Manual time:** about 12 minutes per server
**Frequency:** about 60 times a month

| # | Check | How | Pass if |
|---|-------|-----|---------|
| 1 | Web service | `systemctl is-active nginx` | `active` |
| 2 | App service | `systemctl is-active myapp` | `active` |
| 3 | Web health page | `curl http://localhost/health` | HTTP 200 |
| 4 | App health page | `curl http://localhost:8080/health` | HTTP 200 |
| 5 | Disk | `df -h /` | under 85% used |
| 6 | Memory | `free -m` | available memory above 10% |
| 7 | Load | `uptime` | load reasonable |
| 8 | Recent app errors | `/var/log/myapp/error.log` | report count of `[crit]` lines |

At the end, print a summary table: check, result, PASS/WARN/FAIL. Fail the run if any service or health page is down.
Health checks never change anything on the server.

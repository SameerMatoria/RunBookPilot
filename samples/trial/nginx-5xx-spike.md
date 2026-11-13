# Triage: spike in 5xx errors on the website

**Trigger:** "5xx rate above 2%" alert from monitoring
**Manual time:** 20 minutes
**Frequency:** about 9 times a month

1. Count the 5xx responses in the last 1000 lines of `/var/log/nginx/access.log`.
2. Check whether nginx itself is healthy: `curl http://localhost/health`.
3. Check whether MyApp behind it is healthy: `curl http://localhost:8080/health`.
4. If MyApp is not healthy, restart MyApp and check its health again.
5. If MyApp is healthy but 5xx are still showing, do not restart anything: hand over to the web
   team with the 5xx count and the last 20 lines of `/var/log/nginx/error.log`.
6. Post the findings in the incident channel.

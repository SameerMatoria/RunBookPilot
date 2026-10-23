# Runbook: Restart Nginx web service on app servers

**Owner:** Platform Ops
**When to use:** Website returns 502/503 errors or the "web-down" alert fires.

## Steps

1. SSH into the affected app server (app-web-01 or app-web-02).
2. Check whether nginx is running: `systemctl status nginx`
3. Check free disk space with `df -h /var/log`. If usage is above 90%, clear old logs first.
4. Test the nginx configuration: `sudo nginx -t`. It should say "syntax is ok" and "test is successful".
5. Restart the service: `sudo systemctl restart nginx`
6. Confirm nginx is active: `systemctl is-active nginx` should print `active`.
7. Check the health page: `curl -s -o /dev/null -w "%{http_code}" http://localhost/health` should return 200.
8. Make sure everything looks OK and update the ticket.

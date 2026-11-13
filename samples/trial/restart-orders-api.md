# Restart the Orders API (Node.js)

**Owner:** Commerce squad
**When to use:** Orders API returns 502s or the "orders-api memory > 1.5 GB" alert fires.
**Manual time:** 15 minutes
**Frequency:** about 10 times a month

The Orders API is a Node.js 20 service managed by pm2, running as the `orders` user.

1. Check the process: `pm2 status orders-api`
2. Save the last 200 log lines for the ticket: `pm2 logs orders-api --lines 200 --nostream > /tmp/orders-api-before-restart.log`
3. Check memory used by the app in the pm2 status output.
4. Reload with zero downtime: `pm2 reload orders-api`
5. Check `curl -s http://localhost:3000/healthz` returns `{"status":"ok"}`.
6. If the health check fails after 3 tries, do a full restart: `pm2 restart orders-api`, then check again.
7. Confirm nginx is still proxying: `curl -s -o /dev/null -w "%{http_code}" http://localhost/api/orders/ping` should be 200.

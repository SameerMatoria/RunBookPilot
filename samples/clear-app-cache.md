# Runbook: Clear MyApp cache

**Owner:** Application Support
**When to use:** Users see stale pages or old templates after a release.
**Manual time:** about 15 minutes
**Frequency:** about 20 times a month

1. Check myapp is running first - `systemctl status myapp`.
2. Note how big the cache is: `du -sh /var/cache/myapp`.
3. Stop the app: `sudo systemctl stop myapp`
4. Delete everything inside `/var/cache/myapp/sessions` and `/var/cache/myapp/templates`. Do NOT delete the folders themselves, the app expects them to exist.
5. Start the app again: `sudo systemctl start myapp`
6. Wait a few seconds then check the health endpoint on port 8080 returns 200.
7. Confirm the cache folders are empty (or nearly empty) and the app is serving.

If the app does not come back within 30 seconds, escalate.

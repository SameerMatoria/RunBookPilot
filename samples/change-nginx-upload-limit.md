# Runbook: Raise the nginx upload size limit

**Owner:** Platform Ops
**When to use:** A client change request to allow bigger file uploads (users see "413 Request Entity Too Large").
**Manual time:** about 30 minutes (including backup and rollback check)
**Frequency:** about 6 times a month

This is a configuration change on a live server. Always back up first and roll back if anything fails.

## Steps
1. Back up `/etc/nginx/sites-available/default` to `/etc/nginx/backup/` with a timestamp in the file name.
2. Check whether `client_max_body_size` is already set in that file.
3. Set `client_max_body_size 50m;` inside the `server` block (replace the existing value if there is one, otherwise add it).
4. Test the configuration with `nginx -t`.
5. If the test fails: restore the backup, test again, and stop. Report the failure.
6. If the test passes: reload nginx (reload, not restart, so connections aren't dropped).
7. Confirm nginx is active and `http://localhost/health` returns 200.
8. Confirm the running config contains the new limit (`nginx -T | grep client_max_body_size`).

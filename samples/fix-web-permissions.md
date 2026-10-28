# Runbook: Fix web root file permissions

**Owner:** Platform Ops
**When to use:** Security scan reports world-writable files under the web root, or after a manual deployment.
**Manual time:** about 20 minutes
**Frequency:** about 10 times a month

## Standard
- Web root: `/var/www/html`
- Owner and group: `www-data:www-data`
- Directories: `755`
- Files: `644`
- Nothing under the web root may be world-writable.

## Steps
1. List world-writable files and folders under the web root and note how many there are.
2. Set the owner and group of everything under `/var/www/html` to `www-data:www-data`.
3. Set directories to 755.
4. Set files to 644.
5. The uploads folder needs to be writable by the web server - make sure that still works.
6. Re-run the world-writable check; it must find nothing.
7. Check the site still loads (`curl http://localhost/`).

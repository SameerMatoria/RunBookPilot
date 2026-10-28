#!/usr/bin/env bash
# Seeds the sandbox image with realistic server state for the sample runbooks.
set -euo pipefail

# --- nginx logs: current, recently rotated, and old compressed ones ---
mkdir -p /var/log/nginx
echo "127.0.0.1 - - GET / 200" > /var/log/nginx/access.log
touch /var/log/nginx/access.log.1
for i in 2 3 4 5 6; do
  head -c 200000 /dev/urandom | base64 | gzip > "/var/log/nginx/access.log.$i.gz"
  touch -d "$((i * 4)) days ago" "/var/log/nginx/access.log.$i.gz"
done
gzip -c /dev/null > /var/log/nginx/error.log.2.gz && touch -d "3 days ago" /var/log/nginx/error.log.2.gz

# --- myapp: a second web service on port 8080 (served by its own nginx instance) ---
mkdir -p /var/www/myapp /var/log/myapp /var/cache/myapp/sessions /var/cache/myapp/templates
echo "myapp home" > /var/www/myapp/index.html
cat > /var/log/myapp/error.log <<'EOF'
2026-10-20T03:12:44Z [warn] worker 2 slow request /api/orders 4.2s
2026-10-20T03:14:02Z [error] worker 3 out of memory while rendering report
2026-10-20T03:14:02Z [crit] worker 3 exited with signal 9 (OOM killer)
EOF
echo "2026-10-20T03:10:00Z [info] myapp started" > /var/log/myapp/app.log
for i in 1 2 3; do
  head -c 100000 /dev/urandom | base64 | gzip > "/var/log/myapp/app.log.$i.gz"
  touch -d "$((i * 6)) days ago" "/var/log/myapp/app.log.$i.gz"
done
for i in $(seq 1 40); do head -c 20000 /dev/urandom > "/var/cache/myapp/sessions/sess_$i"; done
for i in $(seq 1 10); do head -c 5000 /dev/urandom > "/var/cache/myapp/templates/tpl_$i.cache"; done

# --- stale temp files ---
for i in $(seq 1 15); do
  head -c 50000 /dev/urandom > "/tmp/upload_$i.tmp"
  touch -d "$((i + 2)) days ago" "/tmp/upload_$i.tmp"
done
touch /tmp/upload_current.tmp

# --- TLS certificate that expires in 20 days (inside the 30-day warning window) ---
mkdir -p /etc/ssl/app
openssl req -x509 -newkey rsa:2048 -nodes -days 20 -subj "/CN=app.example.internal" \
  -keyout /etc/ssl/app/app.key -out /etc/ssl/app/app.crt 2>/dev/null
chmod 600 /etc/ssl/app/app.key

# --- web root with loose, wrong permissions (for the permissions runbook) ---
mkdir -p /var/www/html/assets /var/www/html/uploads
echo "<h1>App</h1>" > /var/www/html/index.html
echo "body{}" > /var/www/html/assets/site.css
echo "data" > /var/www/html/uploads/report.csv
chown -R root:root /var/www/html
chmod -R 777 /var/www/html

# --- nginx config backup folder used by config-change runbooks ---
mkdir -p /etc/nginx/backup

# RunbookPilot sandbox: a disposable Linux "app server" that generated scripts are tested on.
# Every test run gets a fresh container that is thrown away. The image is seeded with realistic
# state (old logs, an expiring certificate, loose file permissions) so runbook branches really run.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       nginx curl sudo procps findutils gawk ca-certificates openssl iproute2 tar gzip \
    && rm -rf /var/lib/apt/lists/*

# Containers have no systemd, so a small stand-in answers systemctl for nginx and myapp.
COPY systemctl sandbox-init /usr/local/bin/
COPY nginx-default.conf /etc/nginx/sites-available/default
COPY myapp-nginx.conf /etc/myapp/nginx.conf
COPY seed.sh /tmp/seed.sh
RUN sed -i 's/\r$//' /usr/local/bin/systemctl /usr/local/bin/sandbox-init /tmp/seed.sh /etc/myapp/nginx.conf \
    && chmod +x /usr/local/bin/systemctl /usr/local/bin/sandbox-init \
    && bash /tmp/seed.sh && rm /tmp/seed.sh

WORKDIR /root

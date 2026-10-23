# RunbookPilot sandbox: a disposable Linux "app server" that generated scripts are tested on.
# Mirrors the sample target (Debian + nginx). Every test run gets a fresh container that is thrown away.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx curl sudo procps findutils gawk ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Containers have no systemd, so a small stand-in answers systemctl for nginx.
COPY systemctl /usr/local/bin/systemctl
COPY nginx-default.conf /etc/nginx/sites-available/default
RUN sed -i 's/\r$//' /usr/local/bin/systemctl \
    && chmod +x /usr/local/bin/systemctl \
    && mkdir -p /var/log/nginx \
    && touch /var/log/nginx/access.log.1 && gzip -c /dev/null > /var/log/nginx/access.log.2.gz

WORKDIR /root

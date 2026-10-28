# A stand-in "real" server for trying out runs over SSH: the same Debian + nginx + myapp setup and
# seeded state as the sandbox, plus an SSH server and a non-root "ops" user with sudo.
# DEMO ONLY: the ops password is public. Never expose this container beyond your machine.
# Build from the repo root:  docker build -f demo-server/Dockerfile .
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       nginx curl sudo procps findutils gawk ca-certificates openssl iproute2 tar gzip openssh-server \
    && rm -rf /var/lib/apt/lists/*

COPY sandbox/systemctl sandbox/sandbox-init /usr/local/bin/
COPY sandbox/nginx-default.conf /etc/nginx/sites-available/default
COPY sandbox/myapp-nginx.conf /etc/myapp/nginx.conf
COPY sandbox/seed.sh /tmp/seed.sh
COPY demo-server/start.sh /usr/local/bin/start-demo-server
RUN sed -i 's/\r$//' /usr/local/bin/systemctl /usr/local/bin/sandbox-init /usr/local/bin/start-demo-server \
         /tmp/seed.sh /etc/myapp/nginx.conf \
    && chmod +x /usr/local/bin/systemctl /usr/local/bin/sandbox-init /usr/local/bin/start-demo-server \
    && bash /tmp/seed.sh && rm /tmp/seed.sh

# The account RunbookPilot connects as: not root, with passwordless sudo (like most managed servers).
ARG OPS_PASSWORD=runbookpilot-demo
RUN useradd --create-home --shell /bin/bash ops \
    && echo "ops:${OPS_PASSWORD}" | chpasswd \
    && echo "ops ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/ops && chmod 440 /etc/sudoers.d/ops \
    && mkdir -p /run/sshd /home/ops/.ssh && chmod 700 /home/ops/.ssh && chown -R ops:ops /home/ops/.ssh \
    && sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication yes/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config

EXPOSE 22
CMD ["start-demo-server"]

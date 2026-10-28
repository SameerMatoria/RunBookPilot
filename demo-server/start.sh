#!/usr/bin/env bash
# Start the app services, an optional authorized SSH key for "ops", then the SSH server.
set -e
sandbox-init
if [ -n "${OPS_AUTHORIZED_KEY:-}" ]; then
  echo "$OPS_AUTHORIZED_KEY" > /home/ops/.ssh/authorized_keys
  chown ops:ops /home/ops/.ssh/authorized_keys && chmod 600 /home/ops/.ssh/authorized_keys
fi
exec /usr/sbin/sshd -D -e

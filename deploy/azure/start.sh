#!/usr/bin/env bash
# Start a paused VM. The containers restart by themselves (restart: unless-stopped).
set -euo pipefail
source "$(dirname "$0")/config.sh"

az vm start -g "$RG" -n "$VM" -o none
echo "Started. RunbookPilot will be back at https://$(fqdn) within a minute or two."

#!/usr/bin/env bash
# Pause the VM. A deallocated VM costs nothing for compute; only its disk and public IP (a few
# dollars a month) are still billed. Data is kept. Start it again with deploy/azure/start.sh.
set -euo pipefail
source "$(dirname "$0")/config.sh"

az vm deallocate -g "$RG" -n "$VM" -o none
echo "Stopped $VM. Compute billing has stopped; data is kept."

#!/usr/bin/env bash
# Delete everything RunbookPilot created on Azure: the whole resource group, including the VM, its
# disk (and the database on it) and the public IP. This can't be undone.
set -euo pipefail
source "$(dirname "$0")/config.sh"

read -r -p "Type the resource group name ($RG) to delete it and everything in it: " answer
[[ "$answer" == "$RG" ]] || { echo "Not deleted."; exit 1; }
az group delete -n "$RG" --yes --no-wait
echo "Deleting $RG in the background. Check with: az group exists -n $RG"

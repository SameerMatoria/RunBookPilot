#!/usr/bin/env bash
# Put RunbookPilot on Azure: the same Docker setup as on a laptop, on one Linux VM, behind HTTPS.
# The first run creates the resource group and VM; later runs just update the code and restart.
# Run from Git Bash in the repo root after `az login`. See deploy/azure/README.md.
set -euo pipefail
source "$(dirname "$0")/config.sh"

[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE, the server's settings (see deploy/azure/README.md)."; exit 1; }

if ! az vm show -g "$RG" -n "$VM" -o none 2>/dev/null; then
  my_ip=$(curl -fsS https://api.ipify.org)
  dns_label="runbookpilot-$(az account show --query id -o tsv | sha1sum | cut -c1-6)"
  echo "Creating resource group $RG and VM $VM ($SIZE) in $LOCATION ..."
  az group create -n "$RG" -l "$LOCATION" -o none
  az vm create -g "$RG" -n "$VM" --image Ubuntu2404 --size "$SIZE" \
    --admin-username "$ADMIN_USER" --generate-ssh-keys \
    --public-ip-sku Standard --public-ip-address-dns-name "$dns_label" \
    --storage-sku StandardSSD_LRS --os-disk-size-gb 30 \
    --nsg-rule NONE --custom-data deploy/azure/cloud-init.yaml -o none
  # Only the website is public. SSH is allowed from this computer's current IP address only.
  az network nsg rule create -g "$RG" --nsg-name "${VM}NSG" -n ssh-from-my-ip --priority 100 \
    --source-address-prefixes "$my_ip" --destination-port-ranges 22 --protocol Tcp -o none
  az network nsg rule create -g "$RG" --nsg-name "${VM}NSG" -n web --priority 110 \
    --destination-port-ranges 80 443 --protocol Tcp -o none
fi

host=$(fqdn)
target="$ADMIN_USER@$host"
ssh_opts=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)

echo "Waiting for the VM to finish its first-boot setup (installing Docker) ..."
until ssh "${ssh_opts[@]}" "$target" true 2>/dev/null; do sleep 10; done
ssh "${ssh_opts[@]}" "$target" "cloud-init status --wait >/dev/null || true; docker compose version >/dev/null" \
  || { echo "Docker isn't ready on the VM. Check: ssh $target 'cloud-init status --long'"; exit 1; }

echo "Fetching branch $BRANCH on the VM ..."
ssh "${ssh_opts[@]}" "$target" "test -d runbookpilot || git clone -q $REPO runbookpilot
  cd runbookpilot && git fetch -q origin $BRANCH && git checkout -q -B $BRANCH origin/$BRANCH"

echo "Copying the server's settings ($ENV_FILE) ..."
scp -q "${ssh_opts[@]}" "$ENV_FILE" "$target:runbookpilot/backend/.env"

echo "Building and starting the containers (the first build takes a few minutes) ..."
ssh "${ssh_opts[@]}" "$target" "cd runbookpilot && chmod 600 backend/.env && echo SITE_ADDRESS=$host > .env && $COMPOSE up -d --build && $COMPOSE ps"

cat <<EOF

RunbookPilot is running at https://$host
(the HTTPS certificate is fetched on the first visit, which can take a minute).

First deployment only: create the admin account (you'll be asked for a password):
  ssh -t $target "cd runbookpilot && docker compose exec api python -m app.users_cli create admin --roles admin"

Pause the VM when you're not using it:   deploy/azure/stop.sh
Delete everything on Azure:              deploy/azure/teardown.sh
EOF

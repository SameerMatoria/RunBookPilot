# Settings shared by the Azure scripts. Override any of them with an environment variable,
# e.g.  LOCATION=eastus deploy/azure/deploy.sh
RG=${RG:-rg-runbookpilot}
LOCATION=${LOCATION:-centralindia}
VM=${VM:-runbookpilot-vm}
SIZE=${SIZE:-Standard_B2s}
ADMIN_USER=azureuser
BRANCH=${BRANCH:-azure-deployment}
REPO=${REPO:-https://github.com/SameerMatoria/RunBookPilot.git}
ENV_FILE=${ENV_FILE:-backend/.env.azure}
COMPOSE="docker compose -f docker-compose.yml -f deploy/azure/docker-compose.azure.yml"

cd "$(dirname "${BASH_SOURCE[0]}")/../.."  # repo root

command -v az >/dev/null || { echo "The Azure CLI isn't installed: winget install Microsoft.AzureCLI, then az login"; exit 1; }

fqdn() { az vm show -d -g "$RG" -n "$VM" --query fqdns -o tsv; }

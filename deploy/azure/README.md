# RunbookPilot on Azure

The same Docker setup as on a laptop, on one Linux VM, with HTTPS in front. Nothing is
re-architected, so Azure behaves exactly like the local demo.

```
Internet ──HTTPS──> caddy ──> web (React) ──> api (FastAPI) ──> db (Postgres)
                                               worker ──> sandbox containers (Docker on the VM)
                                               worker ──SSH──> demo-server
```

- **Public:** only ports 80 and 443 (80 just redirects to HTTPS). SSH (22) is open to the IP address
  of the computer that ran `deploy.sh`, nothing else.
- **Private:** the database, API and demo server are only reachable inside the VM.
- **HTTPS:** a free Let's Encrypt certificate for the VM's Azure DNS name
  (`runbookpilot-xxxxxx.<region>.cloudapp.azure.com`), renewed automatically by Caddy.
- **Session cookies** are marked Secure, so they're only ever sent over HTTPS.

## Cost (Central India, pay-as-you-go, November 2026)

| Item | Price | Billed while stopped? |
|---|---|---|
| VM Standard_B2s (2 vCPU, 4 GB) | $0.0448 / hour (about $1.08 / day) | No |
| 32 GB Standard SSD disk | about $3 / month | Yes |
| Standard public IP | $0.005 / hour (about $3.65 / month) | Yes |

Running it around the clock for two weeks costs about $18; stopped when not in use, a few dollars a
month. Delete everything with `teardown.sh` when the hackathon is over.

## One-time setup

1. Install the Azure CLI and sign in:
   ```
   winget install Microsoft.AzureCLI
   az login
   ```
2. Set a budget with email alerts: Azure portal → **Cost Management** → **Budgets** → **Add**,
   amount $100 a month, alerts at 25%, 50% and 100%.
3. `backend/.env.azure` holds the server's settings (AI keys, and its own SECRET_KEY and MASTER_KEY).
   It is git-ignored. Back up its MASTER_KEY: without it, server logins saved on Azure can't be read.

## Deploy, update, pause, delete

Run these from Git Bash in the repo root, on the `azure-deployment` branch, after pushing it:

| Command | What it does |
|---|---|
| `deploy/azure/deploy.sh` | First run: creates the resource group `rg-runbookpilot` and the VM, then starts the app. Later runs: pull the latest code on the branch and restart. |
| `deploy/azure/stop.sh` | Pauses (deallocates) the VM. Compute billing stops; data is kept. |
| `deploy/azure/start.sh` | Starts it again; the app comes back by itself. |
| `deploy/azure/teardown.sh` | Deletes the resource group and everything in it. Can't be undone. |

Settings such as the region or VM size can be overridden: `LOCATION=eastus deploy/azure/deploy.sh`.
If your IP address changes, update the `ssh-from-my-ip` rule in the VM's network security group.

## After the first deployment

1. Create the admin account (the script prints this command):
   `ssh -t azureuser@<dns name> "cd runbookpilot && docker compose exec api python -m app.users_cli create admin --roles admin"`
2. Sign in at `https://<dns name>`, then on **Servers** add a credential (password, user `ops`,
   password `runbookpilot-demo`) and a server `demo-server`, hostname `demo-server`, port 22,
   and click **Test connection**. The demo server is only reachable from inside the VM.
3. Add any other users (approvers) on **Users**.

The Azure copy starts with an empty database; it doesn't copy the laptop's runbooks.

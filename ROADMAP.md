# RunbookPilot roadmap: from prototype to product

The prototype proves the core loop: runbook in, tested script out, a human approves. This roadmap
turns it into a product a managed-services team could run every day, deployed on Azure as in the
[blueprint](RunbookPilot-Blueprint.html).

## Budget rule

We have **$250 of Azure credits in total**, and they must last through the hackathon presentation.

- Everything is built and tested **locally first**, with Docker Compose standing in for the Azure
  services. Local development costs nothing.
- Azure deployment comes **late** (phase 5), on the cheapest tiers: Container Apps that scale to
  zero, a Burstable Postgres server that can be stopped, the free tier of Static Web Apps, and a free
  AI model unless the pitch needs Azure AI Foundry.
- Budget alerts at $25, $50 and $100, and a one-command teardown.

## Phases

Each phase ends with a working product; nothing is half-built between phases.

### Phase 1: Production backbone (done)
- **Postgres database** instead of JSON files: runbooks, script versions, test runs, approvals and
  the activity log in proper tables, with migrations (Alembic).
- **Job queue and a separate worker process** instead of background threads, so work survives
  restarts and can scale out. The queue lives in Postgres, so there's no Redis to pay for.
- **Docker Compose** for the whole stack: database, API, worker and web app.
- **Automated tests** (pytest, with the AI model and sandbox faked) and **CI** on GitHub Actions.

### Phase 2: Login and roles (done)
- Sign-in with Microsoft accounts (Entra ID), plus a local login for development.
- Roles: **submitter** (uploads runbooks), **approver** (approves scripts), **operator** (runs
  approved scripts on servers), **admin** (manages servers and users).
- Approvals tied to the signed-in identity; the two-approver rule for high-risk scripts uses real
  users; nobody approves their own submission.
- An audit log page: who did what, when.

### Phase 3: Running on real servers (done)
- **Server inventory**: servers, groups (e.g. one per client account) and OS.
- **Secrets** in Azure Key Vault (an encrypted local store during development); never in scripts.
- **Execution** of approved script versions over SSH, dry run first, with live output, run history
  and a per-step result for every run.
- Optional **schedules** and **alert-triggered runs** (a monitoring webhook starts an approved script).
- **Measured metrics**: real run counts and durations replace the estimates on the Impact page.

### Phase 4: Work well on Linux
Linux only, by choice: make the core reliable on real runbooks instead of adding platforms.
- **Trial on real runbooks**: record which end up tested, draft only, needing an engineer, or failed,
  and let the results set the priorities below.
- **Sandbox built from what the runbook needs**: required services and versions come from the real
  server (read-only SSH check), the runbook, or the engineer, and are never guessed. Images are built
  with network access from an approved package list; tests still run with no network.
- **Review card says what was tested**: for example "Debian 12, Node 20, placeholder app".
- **Clear refusal of Windows runbooks**: the Parser already labels them; stop there and say why,
  instead of writing a Bash script for a Windows server.
- **Lint gate catches hidden commands**, such as `base64 -d | bash` and `curl | bash`.
- **Rollback**: scripts back up what they change and restore it if a later step fails.

### Phase 5: Azure deployment
- **Sandbox driver for Azure Container Apps Jobs** (the API never talks to Docker; workers report the sandbox status).
- **Bicep templates**: Container Apps (API and worker), Container Apps Jobs (sandbox), Static Web Apps
  (web app), Postgres Flexible Server, Key Vault, Container Registry, Application Insights.
- **GitHub Actions** deploy pipeline, budget alerts, and `deploy` / `teardown` scripts.
- Optional switch of the AI model to Azure AI Foundry (one setting).

### Phase 6: Microsoft Teams
- **Teams approval cards**: a script ready for review posts a card to Teams with its summary and risk.
- Approving from Teams follows the same rules as the web app: a signed-in approver, never the uploader,
  and two approvers for high-risk scripts.

## Not planned
Dropped so the effort goes into Linux quality: PowerShell and Windows servers, the script library in
Git, ServiceNow / Jira, and Confluence / SharePoint import.

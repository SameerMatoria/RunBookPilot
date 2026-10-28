# Runbook: Give a new developer access to a server

**Owner:** Access Management
**When to use:** An approved access request ticket for a developer.
**Manual time:** about 20 minutes
**Frequency:** about 12 times a month

Inputs from the ticket: username (example: `jdoe`), full name, and the developer's public SSH key.

## Steps
1. Make sure the group `developers` exists; create it if it doesn't.
2. If the user already exists, stop and just confirm their groups - don't recreate them.
3. Create the user with a home directory and bash as the shell, with the full name as the comment.
4. Add the user to the `developers` group.
5. Set up their SSH key: create `~/.ssh` (permission 700) and put the public key in `~/.ssh/authorized_keys` (permission 600), owned by the user.
6. Do not set a password. The account should log in with the SSH key only.
7. Check: `id <username>` shows the developers group, and the key file has the right owner and permissions.
8. Update the access ticket.

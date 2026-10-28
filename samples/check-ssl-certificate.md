# Runbook: Check TLS certificate expiry

**Owner:** Security Ops
**When to use:** Weekly certificate review, or when a client reports a browser certificate warning.
**Manual time:** about 10 minutes
**Frequency:** about 40 times a month (weekly, per client)

## Steps

1. The app certificate lives at `/etc/ssl/app/app.crt`. Confirm the file exists.
2. Read the expiry date: `openssl x509 -enddate -noout -in /etc/ssl/app/app.crt`
3. Read the subject (who it was issued for): `openssl x509 -subject -noout -in /etc/ssl/app/app.crt`
4. Work out how many days are left until expiry.
5. If fewer than 30 days are left, flag it as a WARNING. If it has already expired, flag it as CRITICAL. Otherwise it is OK.
6. Check that the private key `/etc/ssl/app/app.key` is not readable by other users (permissions should be 600 or stricter).
7. Write a one-line summary: subject, expiry date, days left, status.

This runbook is read-only. Do not renew or replace the certificate here; renewal has its own change process.

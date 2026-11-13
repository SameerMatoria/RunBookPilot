# Rotate the payment provider API key

**When to use:** the security team reports the key may have leaked, or the quarterly rotation is due.
**Manual time:** 25 minutes
**Frequency:** about 2 times a month across all accounts
**Risk:** high: a wrong key stops all payments.

The new key is issued by the security team through the vault; never paste it into tickets or chat.

1. Back up `/etc/myapp/app.env` next to itself with today's date in the name.
2. Replace the value of `PAYMENT_API_KEY` in `/etc/myapp/app.env` with the new key.
3. Make sure the file is owned by root and only readable by root (mode 600).
4. Restart MyApp so it reads the new key.
5. Check the health page on port 8080 returns 200.
6. If it doesn't, put the backup back, restart MyApp again and tell the security team.
7. Confirm in the change ticket that the rotation is done (never include the key).

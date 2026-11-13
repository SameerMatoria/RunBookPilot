# Force a MyApp log rotation

**When to use:** app.log has grown past 1 GB before the nightly rotation ran.
**Manual time:** 10 minutes
**Frequency:** about 5 times a month

1. Check the size of `/var/log/myapp/app.log`.
2. Check the logrotate config for MyApp exists: `cat /etc/logrotate.d/myapp`.
3. Do a dry run first to see what would happen: `logrotate -d /etc/logrotate.d/myapp`.
4. Force the rotation: `sudo logrotate -f /etc/logrotate.d/myapp`.
5. Confirm a new, small `app.log` exists and the old one was renamed to `app.log.1`.
6. Make sure MyApp is still running and writing to the new file.

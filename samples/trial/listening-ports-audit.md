# Monthly audit: unexpected listening ports

**Owner:** Security Operations
**Manual time:** 20 minutes per server
**Frequency:** monthly on each web server (about 30 runs a month across the estate)

Only these ports may listen on a web server: **22** (SSH), **80** (nginx) and **8080** (MyApp).

1. List every listening TCP port and the process behind it.
2. Compare the list with the allowed ports above.
3. For any port not on the list, record the port, process name and PID in the audit sheet.
4. Do **not** stop anything. Unexpected ports are investigated by Security, not by this runbook.
5. If everything matches, record "clean" for the server.

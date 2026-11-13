# Recycle the IIS application pool on the Windows web servers

**When to use:** the Customer Portal returns HTTP 503.
**Manual time:** 10 minutes
**Frequency:** about 8 times a month

1. RDP to the affected server (WIN-WEB-01 or WIN-WEB-02).
2. Open PowerShell as Administrator and run `Import-Module WebAdministration`.
3. Check the pool state: `Get-WebAppPoolState -Name "PortalPool"`.
4. Recycle it: `Restart-WebAppPool -Name "PortalPool"`.
5. Check `Invoke-WebRequest http://localhost/portal/health` returns 200.
6. Check the Application event log for new errors from source "ASP.NET".

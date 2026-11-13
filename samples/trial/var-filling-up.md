# /var filling up on the web boxes

_Last edited by Priya, March. Copied from the old wiki, some bits may be out of date._

This happens every couple of weeks on the web tier, usually after a busy weekend. The monitoring
alert says "/var above 85%". Nine times out of ten it's logs and the app's session files.

First have a look at what is actually using the space, du on /var is fine, don't bother with the
whole disk. If it's the journal, vacuum it down to the last 3 days. Old compressed nginx logs can go
if they're more than a week old, same for the myapp ones. The app writes session files to its cache
folder and never cleans them up, anything older than a day is safe to remove - when you run the
delete it may ask you to confirm each file, just say yes.

Don't touch the current access.log and error.log, nginx keeps them open.

Afterwards check the usage again and make sure both web services are still up, then close the alert.
Takes about 15 min if nothing weird is going on. We get this alert roughly 12 times a month across
the estate.

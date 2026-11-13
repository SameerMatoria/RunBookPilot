# Stuck report workers

Report generation sometimes leaves `report-worker` processes hanging and they slowly eat CPU.
About 15 minutes by hand, roughly 6 times a month.

1. List report-worker processes with their age and CPU: `ps -eo pid,etimes,pcpu,args | grep [r]eport-worker`
2. Any that have been running for more than 2 hours are stuck.
3. Send the stuck ones a normal kill first, wait 10 seconds, then kill -9 anything still there.
4. Do not touch processes that belong to other services.
5. List the processes again to confirm the stuck ones are gone, and note how many were killed.

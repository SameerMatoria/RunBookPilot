# Check PostgreSQL connection saturation

**When to use:** application errors say "too many connections", or the DB connections alert fires.
**Manual time:** 15 minutes
**Frequency:** about 8 times a month

All commands run on the database server as the `postgres` user.

1. Get the connection limit: `psql -c "SHOW max_connections;"`
2. Count current connections by state:
   `psql -c "SELECT state, count(*) FROM pg_stat_activity GROUP BY state;"`
3. List sessions that have been idle in transaction for more than 10 minutes, with their
   application name and client address.
4. If total connections are above 90% of the limit, terminate the idle-in-transaction sessions from
   step 3 with `pg_terminate_backend`. Never terminate sessions from the `replication` user.
5. Count connections again and record before/after numbers in the ticket.

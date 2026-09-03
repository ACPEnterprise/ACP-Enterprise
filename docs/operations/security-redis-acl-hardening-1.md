# SECURITY.REDIS.ACL.HARDENING.1

Preview Redis is Docker-network internal and requires named ACL identities.
Credentials live only in the owner-controlled host directory configured by
`REDIS_SECRET_DIR_HOST`; the directory is mounted read-only into Redis and the
backend. No password is stored in Git or in the Compose environment.

A separately stored `acp-breakglass` administrator is available only to the
host owner for ACL recovery. Its plaintext credential is not mounted into any
application container; only its password hash is present in the Redis ACL file.

`acp-application` is limited to `PING`, transactional rate-limit commands, and
`auth-rate:*` keys. `acp-health` can only execute `PING`. The generated ACL must
disable the default user and deny administrative and destructive commands,
including `CONFIG`, `MODULE`, `REPLICAOF`, `SLAVEOF`, `SHUTDOWN`, `FLUSHALL`,
`FLUSHDB`, `DEBUG`, and `MIGRATE`.

Redis stores rate-limit coordination only; durable business authority remains
in PostgreSQL. Preview therefore disables RDB/AOF persistence. This prevents
historical anonymous transactions from being replayed after the default ACL
identity is disabled. The pre-cutover persistence volume remains available as
incident evidence but is not consumed by the hardened runtime.

Cutover keeps the existing Redis volume. Create the mounted secret directory as
root-owned mode `0755`, the application password as mode `0640` for the backend
runtime group, and the hashed ACL file and health-only password as mode `0644`
so the unprivileged Redis runtime can read them. Validate a candidate Redis container, update backend and Mission
Control one at a time, and disable the default user only after every consumer
is authenticated. Rollback retains the pre-cutover inspect, image identity,
environment capture, and prior container configuration until acceptance.

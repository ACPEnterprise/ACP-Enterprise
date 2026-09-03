# Platform Redis Runtime Qualification 1

## Runtime authority

ACP uses Redis for authentication abuse-rate coordination and platform readiness. PostgreSQL remains durable business authority. Redis is required for authentication safeguards and therefore fails closed when unavailable; optional future Redis consumers must retain their own explicit degradation classification.

Local development and Preview continue to use their existing private `redis:7-alpine` service and `REDIS_URL`. Deterministic integration qualification uses `docker-compose.redis-qualification.yml`, an isolated Compose project, Redis database 15, ephemeral PostgreSQL and Redis storage, health-gated startup, and unconditional teardown.

Run from the repository root:

```sh
./scripts/qualify-redis-runtime
```

The runner validates Compose configuration, starts fresh services, upgrades PostgreSQL to the current Alembic head, executes real Redis integration coverage, and removes its containers, network, and volumes. It publishes no Redis or PostgreSQL host ports and does not use an in-memory substitute.

## Qualified behavior

- Redis connection, close, and subsequent reconnect use the authoritative async client.
- Authentication counters increment atomically in a Redis transaction, retain a bounded TTL, isolate identities, and deny requests above the limit.
- Redis unavailability raises the bounded authentication-unavailable classification instead of bypassing protection or exposing connection details.
- Platform readiness reports required Redis as healthy only after a real ping.
- JSON serialization and deserialization are explicitly round-tripped without granting Redis durable business authority.
- Tests use unique synthetic keys and deterministic cleanup; the Compose runtime itself is ephemeral.

No caching redesign, queue redesign, provider admission, Preview deployment, or Production mutation is part of this milestone.

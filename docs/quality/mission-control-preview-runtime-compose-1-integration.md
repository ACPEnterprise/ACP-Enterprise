# Mission Control Preview runtime Compose 1 — Enterprise Release handoff

## Candidate

- Starting protected authority: `63e4ac863763e00a3090e172a43fc32e5feb17da`
- Scope: make the accepted Mission Control web/API release reproducible and coherent
  inside the existing Preview Compose authority.
- Schema impact: none.
- Preview deployment performed: no.
- Production impact: none.

## Proven live defect

The live Mission Control web container restart-loops because its Nginx artifact uses
the canonical `backend:8000` upstream while the isolated Docker network provides no
`backend` alias. The live API is also stale: it reports version `0b74c765...` and
expected platform fingerprint `f0c90b...`, while the healthy tenant backend reports
version `e4947b66...` and fingerprint `d7d2db...`. Its health endpoint returns 503
despite PostgreSQL and Redis connectivity. Preview `/mission-control` consequently
returns 502.

The pair lacks Compose ownership metadata and protected source contained no service
definition capable of recreating it safely. That made alias, artifact-lineage and
restart drift likely to recur.

## Repair

`docker-compose.preview.yml` now defines an optional `mission-control` profile:

- API and web are built together from the current protected checkout.
- API reuses the canonical backend image, environment, secret mounts, persistence and
  migration dependencies.
- API trusts only the isolated `172.32.0.0/24` proxy network for forwarded headers.
- The required `backend` DNS alias exists only on that isolated network.
- The web container cannot reach the ordinary Preview network directly.
- Only the web service publishes a host port, bound to loopback `127.0.0.1:18008`.
- Web startup waits for a healthy API, so Caddy cannot expose an incoherent pair as a
  nominally successful replacement.

## Controlled adoption

Enterprise Release must preserve current inspect/log evidence and rollback image
references, take the normal Preview backup, build both services from the integrated
protected checkout, and validate the migration/platform fingerprint gates. Remove only
the exact legacy Mission Control containers that conflict with Compose service names,
then start the profile and run `scripts/verify-mission-control-preview.sh`.

Do not modify Caddy, broaden Docker networks, change fingerprints, downgrade schema or
touch the healthy tenant application merely to make Mission Control appear available.

## Qualification

- Mission Control Compose contract tests: passed.
- Existing Preview network-exposure and Beta connectivity contract tests: passed.
- Docker Compose profile validation: passed with the current restricted Preview
  environment through `docker compose ... config --quiet`; Enterprise must repeat it
  from the integrated immutable release before adoption.
- Production and `app.twelve-hats.com`: untouched.

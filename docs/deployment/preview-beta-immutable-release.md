# Preview/Beta immutable application releases

`scripts/deploy-preview-release.py` is the sanctioned Preview/Beta application
deployer. It is intentionally not a Production tool. The source checkout used
to build a release is separate from the runtime directories; neither
`/opt/acp-enterprise/current` nor any `/opt/acp-enterprise/releases/enterprise-beta-*`
directory is expected to contain `.git`.

The controlled source checkout is `/opt/acp-enterprise/builder`. It must be a
clean checkout of this repository and is never used as a running application.
The deployer uses `git archive` at the requested full commit SHA, copies only
the prior release's mode-0600 `.env.preview`, sets its `APP_VERSION` to the full
SHA, and records rollback metadata in `.release-metadata.json`.

The first version deploys the `backend` service. Additional application
services may be requested with repeated `--service` flags, but `backend` is
always required for the version, schema, and health gates. PostgreSQL, Redis,
Alembic migration services, QBO init services, and Production are rejected.

## Dry run

Run from the controlled builder checkout. This performs source, runtime-config,
target-conflict, and Preview-policy checks only; it does not create a release,
build an image, switch `current`, recreate a container, or contact Beta.

```bash
cd /opt/acp-enterprise/builder
python3 scripts/deploy-preview-release.py deploy \
  --source-root /opt/acp-enterprise/builder \
  --root /opt/acp-enterprise \
  --sha 4bfdf3b1d58c7fa3dd2c3871c01f7d5662b0575f \
  --service backend \
  --dry-run
```

## Controlled deploy

Run only after the dry run and the owner-approved Beta deployment decision pass.
The command validates Compose before switching `current`, builds only the
requested application image, switches the symlink atomically, recreates only
the requested application service with `--no-deps`, and verifies the exact
`APP_VERSION`, Alembic current/head/check, backend health, Beta connectivity,
and unchanged PostgreSQL/Redis container IDs.

It never runs `alembic upgrade`, `docker compose restart`, or `docker compose
down`; PostgreSQL and Redis are not targeted.

```bash
cd /opt/acp-enterprise/builder
python3 scripts/deploy-preview-release.py deploy \
  --source-root /opt/acp-enterprise/builder \
  --root /opt/acp-enterprise \
  --sha 4bfdf3b1d58c7fa3dd2c3871c01f7d5662b0575f \
  --service backend
```

The resulting runtime directory is:

```text
/opt/acp-enterprise/releases/enterprise-beta-4bfdf3b1
```

The previous `current` target is retained and recorded in the new release's
metadata. A failed post-switch gate attempts an application-only automatic
rollback and leaves the failed immutable release in place for inspection.

## Explicit rollback

For the currently observed prior release, use:

```bash
cd /opt/acp-enterprise/builder
python3 scripts/deploy-preview-release.py rollback \
  --root /opt/acp-enterprise \
  --to /opt/acp-enterprise/releases/enterprise-beta-48f3911f \
  --service backend
```

Rollback rebuilds only the backend from the selected immutable release,
atomically restores `current`, recreates only backend, and reruns health,
schema, Beta-connectivity, and PostgreSQL/Redis identity checks. It does not
restore database data or downgrade the schema. If the target is omitted, the
deployer reads the prior target recorded by the active release metadata.

Never delete a release, use `docker compose down -v`, invoke a migration, point
the tool at `docker-compose.production.yml`, or set
`QBO_PRODUCTION_ENABLED=true`.

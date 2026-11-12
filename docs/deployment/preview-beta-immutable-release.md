# Preview/Beta immutable application releases

`scripts/deploy-preview-release.py` is the sanctioned Preview/Beta application
deployer. It is intentionally not a Production tool. The source checkout used
to build a release is separate from the runtime directories; neither
`/opt/acp-enterprise/current` nor any `/opt/acp-enterprise/releases/enterprise-beta-*`
directory is expected to contain `.git`.

The controlled source checkout is `/opt/acp-enterprise/builder`. It must be a
clean checkout of this repository and is never used as a running application.
The deployer uses `git archive` at the requested full commit SHA, copies only
the approved mode-0600 `.env.preview`, sets or verifies its `APP_VERSION` to the
full SHA, and records rollback metadata in `.release-metadata.json`.

The first version deploys the `backend` service. Additional application
services may be requested with repeated `--service` flags, but `backend` is
always required for the version, schema, and health gates. PostgreSQL, Redis,
Alembic migration services, QBO init services, and Production are rejected.

## Clean-root bootstrap dry run

Use `bootstrap` exactly once on a new host. The root may already contain the
builder/shared-secrets directories, but `current` must not exist and
`releases/` must be absent or empty. Bootstrap only creates the immutable
release and the `current` symlink; it does not start Docker services, run
migrations, or contact HCP, QBO, Production, DNS, or Beta.

The supplied environment file must already be mode `0600`, Preview-only, and
contain `APP_VERSION` equal to the requested SHA.

```bash
cd /opt/acp-enterprise/builder
python3 scripts/deploy-preview-release.py bootstrap \
  --source-root /opt/acp-enterprise/builder \
  --root /opt/acp-enterprise \
  --sha dc9af03d60ed069993ef613775d033c9f5470a77 \
  --env-file /opt/acp-enterprise/builder/.env.preview \
  --service backend \
  --dry-run
```

## Clean-root bootstrap

Run only after the bootstrap dry run passes. This creates
`/opt/acp-enterprise/releases/enterprise-beta-dc9af03d` and atomically creates
`/opt/acp-enterprise/current`; it still starts no services. Starting the fresh
isolated PostgreSQL/Redis/application stack and performing the one-time isolated
database migration are separate owner actions.

```bash
cd /opt/acp-enterprise/builder
python3 scripts/deploy-preview-release.py bootstrap \
  --source-root /opt/acp-enterprise/builder \
  --root /opt/acp-enterprise \
  --sha dc9af03d60ed069993ef613775d033c9f5470a77 \
  --env-file /opt/acp-enterprise/builder/.env.preview \
  --service backend
```

## Promotion dry run

Run from the controlled builder checkout. This performs source, runtime-config,
target-conflict, and Preview-policy checks only; it does not create a release,
build an image, switch `current`, recreate a container, or contact Beta.

```bash
cd /opt/acp-enterprise/builder
python3 scripts/deploy-preview-release.py deploy \
  --source-root /opt/acp-enterprise/builder \
  --root /opt/acp-enterprise \
  --sha dc9af03d60ed069993ef613775d033c9f5470a77 \
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
  --sha dc9af03d60ed069993ef613775d033c9f5470a77 \
  --service backend
```

The resulting runtime directory is:

```text
/opt/acp-enterprise/releases/enterprise-beta-dc9af03d
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

## November HCP handoff qualification

The metadata-only November OM1C handoff is qualified through the dedicated
authority contract `hcp-november-preview-qualification/v1`. The current sealed
handoff contract is `hcp-clean-beta-admission-handoff/v1`; it is unpacked
privately before qualification. The bundle is custody evidence only; this
command performs no HCP call and no Preview write.

The exact private transfer destination on the clean Beta host is:

```text
/opt/acp-enterprise/shared/hcp-admission/
```

The directory is root-owned mode `0700`. Transfer these mode-0600 files into it:

```text
/opt/acp-enterprise/shared/hcp-admission/hcp-clean-beta-admission-bundle.tar.gz
/opt/acp-enterprise/shared/hcp-admission/hcp-clean-beta-admission-bundle.sha256
/opt/acp-enterprise/shared/hcp-admission/preview-admission-authority.json
```

Unpack only into the root-owned mode-0700 directory
`/opt/acp-enterprise/shared/hcp-admission/qualified-bundle/`, preserving the
exact required file set. Inside the transient qualification container, the
authority refers to the archive as
`/run/hcp-admission/hcp-clean-beta-admission-bundle.tar.gz` and the unpacked
root as `/run/hcp-admission/qualified-bundle`. It must bind the exact bundle
SHA, acquisition/reconciliation/attachment-custody digests, Company/Branch/
actor/HCP Company IDs, Master SHA, and `yp8r0t2v4x6z`. The qualifier derives
and checks the 22 location-less Job holds, 13 duplicate-risk Appointment
holds, 2 unresolved-technician holds, 1 unassigned Appointment hold, and zero
strict-open relationship failures from the sealed reconciliation. Any
unexplained omission, unsafe hold contamination, missing lineage, or digest
mismatch rejects qualification.

Example owner transfer destination:

```bash
scp -i ~/.ssh/acp_beta_clean_ed25519 \
  hcp-clean-beta-admission-bundle.tar.gz hcp-clean-beta-admission-bundle.sha256 \
  preview-admission-authority.json \
  root@162.243.232.59:/opt/acp-enterprise/shared/hcp-admission/
```

Run qualification only after verifying the private files and their modes:

```bash
docker compose \
  --project-name acp-enterprise-preview \
  --env-file /opt/acp-enterprise/current/.env.preview \
  -f /opt/acp-enterprise/current/docker-compose.preview.yml \
  run --rm --no-deps \
  -e TARGET_ENVIRONMENT=preview \
  -e PRODUCTION_ACCESS_ENABLED=false \
  -e PREVIEW_ACCESS_ENABLED=true \
  -v /opt/acp-enterprise/shared/hcp-admission:/run/hcp-admission:ro \
  backend \
  python -m app.operational_migration.hcp_preview_admission_command qualify \
  --authority-file /run/hcp-admission/preview-admission-authority.json
```

Qualification fails closed on bundle SHA/file-digest mismatch, scope or
authority mismatch, missing/ambiguous lineage, an admissible held identity,
blocked clean records, unexplained omissions, or missing attachment custody.
Attachment bodies are not required when the custody manifest and digest pass.
The metadata-only authority cannot execute by itself; a bounded Preview
admission requires the separately sealed execution packet and execution fields
described below.

## November bounded Preview execution

The November qualification bundle is metadata-only and is not itself an
executable record packet. Execution requires a separate private,
mode-0600 `hcp-november-preview-execution-packet/v1` containing the admissible
Customer, Location, Job, and Appointment assertions. It must include every
qualified hold as a non-mutating assertion and bind all of the following to the
PASS qualification: bundle SHA, policy digest, source reconciliation digest,
Company/Branch/actor IDs, Master SHA, schema head, and `preview`.

The authority must additionally contain:

```text
qualification_status=PASS
qualification_digest=<digest printed by qualify>
execution_packet_path=/run/hcp-admission/november-execution-packet.json
execution_packet_sha256=<private packet file SHA-256>
execution_packet_digest=<packet semantic digest>
rollback_backup_digest=<qualified Beta backup SHA-256>
```

The packet is rejected unless its hold inventory exactly matches 22
`HOLD_QUARANTINE` Jobs, 13 duplicate-risk Appointment `HOLD`s, 2 unresolved
technician `HOLD`s, and 1 unassigned Appointment `HOLD`. Financial domains,
held-record writes, release assertions, and missing parent lineage are
unsupported.

After the separate execution packet and authority are sealed, the exact
bounded command is:

```bash
docker compose \
  --project-name acp-enterprise-preview \
  --env-file /opt/acp-enterprise/current/.env.preview \
  -f /opt/acp-enterprise/current/docker-compose.preview.yml \
  run --rm --no-deps --user 0:0 \
  -e TARGET_ENVIRONMENT=preview \
  -e PRODUCTION_ACCESS_ENABLED=false \
  -e PREVIEW_ACCESS_ENABLED=true \
  -e HCP_PROVIDER_WRITE_ENABLED=false \
  -e HCP_LIVE_ACCESS_ENABLED=false \
  -e QBO_PRODUCTION_ENABLED=false \
  -e PAYROLL_EXECUTION_ENABLED=false \
  -v /opt/acp-enterprise/shared/hcp-admission:/run/hcp-admission:ro \
  backend \
  python -m app.operational_migration.hcp_preview_admission_command execute \
  --authorize-execution \
  --authority-file /run/hcp-admission/preview-admission-authority.json
```

The executor uses the existing Preview domain services and atomic overlay
transaction. It acquires a transaction-scoped advisory lock, writes only
admissible assertions, records holds without mutation, and persists the
receipt in the migration replay state. Any exception rolls back all native
rows, bindings, lineage, and receipt state. A repeat with the same packet
returns the identical durable receipt as an idempotent replay.

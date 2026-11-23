#!/usr/bin/env bash
set -Eeuo pipefail

# Build and exercise the assembled application in a disposable Compose project.
# This is deliberately separate from the protected Beta release workflow.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.application-acceptance.yml"
PROJECT="acp_application_acceptance_$$"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/acp-application-acceptance.XXXXXX")"
ENV_FILE="$WORK_DIR/compose.env"
CREDENTIAL_FILE="$WORK_DIR/owner-credentials.json"
SMOKE_TOKEN_FILE="$WORK_DIR/smoke-token"
RECEIPT_FILE="$WORK_DIR/acceptance-receipt.json"

cleanup() {
  set +e
  docker compose --project-name "$PROJECT" --file "$COMPOSE_FILE" --env-file "$ENV_FILE" down --volumes --remove-orphans >/dev/null 2>&1
  rm -rf "$WORK_DIR"
}

on_exit() {
  status=$?
  if [[ "$status" -ne 0 ]]; then
    docker compose --project-name "$PROJECT" --file "$COMPOSE_FILE" --env-file "$ENV_FILE" logs --no-color --tail=120 backend frontend >&2 || true
  fi
  cleanup
  exit "$status"
}
trap on_exit EXIT

umask 077
admin_password="$(openssl rand -hex 32)"
app_password="$(openssl rand -hex 32)"
migrate_password="$(openssl rand -hex 32)"
backup_password="$(openssl rand -hex 32)"
owner_password="$(openssl rand -hex 32)Aa1!"
frontend_port="${ACCEPTANCE_FRONTEND_PORT:-18181}"

printf '%s\n' \
  "ACCEPTANCE_ADMIN_PASSWORD=$admin_password" \
  "ACCEPTANCE_APP_PASSWORD=$app_password" \
  "ACCEPTANCE_MIGRATE_PASSWORD=$migrate_password" \
  "ACCEPTANCE_BACKUP_PASSWORD=$backup_password" \
  "ACCEPTANCE_OWNER_PASSWORD=$owner_password" \
  "ACCEPTANCE_FRONTEND_PORT=$frontend_port" >"$ENV_FILE"

printf '%s\n' '{"email":"acceptance-owner@example.invalid","password":"'"$owner_password"'"}' >"$CREDENTIAL_FILE"
chmod 600 "$ENV_FILE" "$CREDENTIAL_FILE"

compose() {
  docker compose --project-name "$PROJECT" --file "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN=python3
fi

compose up --detach --wait postgres redis
compose run --rm provision-roles
compose run --rm migrate
compose run --rm bootstrap
# Re-running supported bootstrap must be a safe no-op; it must not duplicate
# permissions, roles, memberships, or the initial company.
compose run --rm bootstrap
compose up --detach --wait backend frontend

published_frontend_port="$(compose port frontend 80 | awk -F: 'NF {print $NF; exit}')"
if [[ -z "$published_frontend_port" ]]; then
  echo "frontend did not publish port 80" >&2
  compose ps >&2
  exit 1
fi
echo "frontend published port: $published_frontend_port"

for attempt in {1..30}; do
  if curl --fail --silent "http://127.0.0.1:${published_frontend_port}/healthz" >/dev/null; then
    break
  fi
  if [[ "$attempt" -eq 30 ]]; then
    echo "frontend did not become reachable through its published port" >&2
    compose ps >&2
    compose port frontend 80 >&2
    exit 1
  fi
  sleep 1
done
curl --fail --silent --show-error "http://127.0.0.1:${published_frontend_port}/health/ready" >/dev/null

"$PYTHON_BIN" "$ROOT_DIR/scripts/application-integration-acceptance.py" \
  --base-url "http://127.0.0.1:${published_frontend_port}" \
  --credential-file "$CREDENTIAL_FILE" \
  --receipt "$RECEIPT_FILE" \
  --smoke-token-file "$SMOKE_TOKEN_FILE"

smoke_company_id="$(jq -r '.company_id' "$RECEIPT_FILE")"
smoke_branch_id="$(jq -r '.branch_id' "$RECEIPT_FILE")"
smoke_denied_company_id="$($PYTHON_BIN -c 'import uuid; print(uuid.uuid4())')"
for smoke_check in authentication authorization tenant-isolation; do
  case "$smoke_check" in
    authentication)
      smoke_path=/api/v1/authorization/companies
      ;;
    authorization)
      smoke_path=/api/v1/customers
      ;;
    tenant-isolation)
      smoke_path=/api/v1/customers
      ;;
  esac
  compose run --rm --no-deps --no-TTY \
    --volume "$SMOKE_TOKEN_FILE:/run/acceptance/smoke-token:ro" \
    --env SMOKE_BASE_URL=http://frontend \
    --env SMOKE_COMPANY_ID="$smoke_company_id" \
    --env SMOKE_BRANCH_ID="$smoke_branch_id" \
    --env SMOKE_DENIED_COMPANY_ID="$smoke_denied_company_id" \
    --env SMOKE_DENIED_BRANCH_ID="$smoke_branch_id" \
    backend python /app/scripts/protected_smoke_check.py \
    --check "$smoke_check" \
    --path "$smoke_path" \
    --credential-file /run/acceptance/smoke-token
done

# Restart the assembled services, then perform a fresh authenticated readback.
compose restart backend frontend
for attempt in {1..30}; do
  if curl --fail --silent "http://127.0.0.1:${published_frontend_port}/health/ready" >/dev/null; then
    break
  fi
  if [[ "$attempt" -eq 30 ]]; then
    echo "assembled runtime did not recover after restart" >&2
    compose ps >&2
    exit 1
  fi
  sleep 1
done
"$PYTHON_BIN" "$ROOT_DIR/scripts/application-integration-acceptance.py" \
  --base-url "http://127.0.0.1:${published_frontend_port}" \
  --credential-file "$CREDENTIAL_FILE" \
  --receipt "$RECEIPT_FILE" \
  --readback

# Prove the runtime identity, role attributes, and RLS posture from inside the
# actual backend.  A username-only assertion is insufficient: an elevated
# role could make the rest of the acceptance evidence meaningless.
compose exec --no-TTY backend python - <<'PY'
import asyncio
from sqlalchemy import text
from app.database.session import AsyncSessionFactory

async def main():
    async with AsyncSessionFactory() as session:
        identity = await session.execute(text("""
            SELECT current_user,
                   current_setting('row_security'),
                   current_setting('app.company_id', true),
                   r.rolsuper,
                   r.rolcreaterole,
                   r.rolcreatedb,
                   r.rolreplication,
                   r.rolbypassrls
            FROM pg_roles AS r
            WHERE r.rolname = current_user
        """))
        row = identity.one()
        if row[0] != "acp_app":
            raise SystemExit(f"unexpected runtime database identity: {row[0]}")
        if row[1] != "on":
            raise SystemExit(f"row security is not enabled: {row[1]}")
        if any(row[index] for index in range(3, 8)):
            raise SystemExit("acp_app has an elevated PostgreSQL role attribute")
        print("runtime database identity, least privilege, and row security: PASS")

asyncio.run(main())
PY

# Prove the image contains every executable used by the governed database,
# runtime, and protected-smoke paths. The HTTP acceptance above exercises the
# real routes; this check prevents a release image from silently omitting a
# verifier or substituting a host-only checkout.
compose exec --no-TTY backend python - <<'PY'
from pathlib import Path

executables = (
    Path("/app/scripts/protected-database-security-probe.py"),
    Path("/app/scripts/protected-runtime-check.py"),
    Path("/app/scripts/protected-smoke-check.py"),
    Path("/app/scripts/protected_smoke_check.py"),
)
missing = [str(path) for path in executables if not path.is_file()]
if missing:
    raise SystemExit(f"release executable(s) missing from backend image: {missing}")
import scripts.protected_smoke_check  # noqa: F401

print("backend security and smoke executables plus import: PASS")

PY

# Exercise the real backup principal and an isolated restore. The backup
# identity is separate from the runtime identity and is never used by the
# application. Restore is performed with the disposable database administrator
# into a second database so the running application database is untouched.
backup_dump="$WORK_DIR/application-backup.dump"
compose run --rm --no-deps --no-TTY \
  --env PGPASSWORD="$backup_password" postgres \
  pg_dump --host postgres --username acp_backup --dbname acp_application_acceptance \
  --format=custom --no-owner --no-acl >"$backup_dump"
if [[ ! -s "$backup_dump" ]]; then
  echo "backup principal produced an empty dump" >&2
  exit 1
fi
compose exec --no-TTY --env PGPASSWORD="$admin_password" postgres \
  psql -v ON_ERROR_STOP=1 -U acceptance_admin -d postgres \
  -c 'CREATE DATABASE acceptance_restore'
compose run --rm --no-deps --no-TTY \
  --env PGPASSWORD="$admin_password" postgres \
  pg_restore --host postgres --username acceptance_admin --dbname acceptance_restore \
  --no-owner --no-acl --exit-on-error <"$backup_dump"
restored_tables="$(compose run --rm --no-deps --no-TTY \
  --env PGPASSWORD="$admin_password" postgres \
  psql --host postgres --username acceptance_admin --dbname acceptance_restore \
  --tuples-only --no-align --command \
  'SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname = '\''public'\''')"
if [[ "${restored_tables//[[:space:]]/}" -le 0 ]]; then
  echo "isolated restore did not contain application tables" >&2
  exit 1
fi
echo "backup and isolated restore: PASS ($restored_tables public tables)"

printf '%s\n' 'application integration acceptance: PASS'

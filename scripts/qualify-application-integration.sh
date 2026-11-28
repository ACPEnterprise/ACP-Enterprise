#!/usr/bin/env bash
set -Eeuo pipefail

# Build and exercise the assembled application in a disposable Compose project.
# This is deliberately separate from the protected Beta release workflow.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.application-acceptance.yml"
COMPOSE_FILES=(--file "$COMPOSE_FILE")
if [[ -n "${ACCEPTANCE_COMPOSE_OVERRIDE:-}" ]]; then
  if [[ ! -f "$ACCEPTANCE_COMPOSE_OVERRIDE" ]]; then
    echo "acceptance Compose override was not found" >&2
    exit 1
  fi
  COMPOSE_FILES+=(--file "$ACCEPTANCE_COMPOSE_OVERRIDE")
fi
PROJECT="acp_application_acceptance_$$"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/acp-application-acceptance.XXXXXX")"
ENV_FILE="$WORK_DIR/compose.env"
CREDENTIAL_FILE="$WORK_DIR/owner-credentials.json"
SMOKE_TOKEN_FILE="$WORK_DIR/smoke-token"
RECEIPT_FILE="$WORK_DIR/acceptance-receipt.json"
SMOKE_CUSTODY_VOLUME="${PROJECT}-smoke-custody"
PRINCIPAL_CUSTODY_VOLUME="${PROJECT}-principal-custody"

cleanup() {
  set +e
  docker compose --project-name "$PROJECT" "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" down --volumes --remove-orphans >/dev/null 2>&1
  docker volume rm "$SMOKE_CUSTODY_VOLUME" "$PRINCIPAL_CUSTODY_VOLUME" >/dev/null 2>&1 || true
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

docker volume create --label "com.twelvehats.acceptance.project=$PROJECT" \
  "$SMOKE_CUSTODY_VOLUME" >/dev/null
docker volume create --label "com.twelvehats.acceptance.project=$PROJECT" \
  "$PRINCIPAL_CUSTODY_VOLUME" >/dev/null

umask 077
admin_password="$(openssl rand -hex 32)"
app_password="$(openssl rand -hex 32)"
migrate_password="$(openssl rand -hex 32)"
backup_password="$(openssl rand -hex 32)"
owner_password="$(openssl rand -hex 32)Aa1!"
frontend_port="${ACCEPTANCE_FRONTEND_PORT:-18181}"
owner_email="${ACCEPTANCE_OWNER_EMAIL:-acceptance-owner@example.invalid}"

printf '%s\n' \
  "ACCEPTANCE_ADMIN_PASSWORD=$admin_password" \
  "ACCEPTANCE_APP_PASSWORD=$app_password" \
  "ACCEPTANCE_MIGRATE_PASSWORD=$migrate_password" \
  "ACCEPTANCE_BACKUP_PASSWORD=$backup_password" \
  "ACCEPTANCE_OWNER_PASSWORD=$owner_password" \
  "ACCEPTANCE_OWNER_EMAIL=$owner_email" \
  "ACCEPTANCE_COMPANY_NAME=${ACCEPTANCE_COMPANY_NAME:-TwelveHats Isolated Acceptance}" \
  "ACCEPTANCE_COMPANY_CODE=${ACCEPTANCE_COMPANY_CODE:-ACCEPTANCE}" \
  "QBO_HISTORICAL_ARCHIVE_HOST=${QBO_HISTORICAL_ARCHIVE_HOST:-}" \
  "ACCEPTANCE_FRONTEND_PORT=$frontend_port" >"$ENV_FILE"

printf '%s\n' '{"email":"'"$owner_email"'","password":"'"$owner_password"'"}' >"$CREDENTIAL_FILE"
chmod 600 "$ENV_FILE" "$CREDENTIAL_FILE"

compose() {
  docker compose --project-name "$PROJECT" "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" "$@"
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

published_frontend_port="$frontend_port"
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

acceptance_args=()
if [[ "${REVENUE_CYCLE_ACCEPTANCE:-false}" == "true" ]]; then
  acceptance_args+=(--revenue-cycle)
fi

"$PYTHON_BIN" "$ROOT_DIR/scripts/application-integration-acceptance.py" \
  --base-url "http://127.0.0.1:${published_frontend_port}" \
  --credential-file "$CREDENTIAL_FILE" \
  --receipt "$RECEIPT_FILE" \
  --smoke-token-file "$SMOKE_TOKEN_FILE" \
  "${acceptance_args[@]}"

if [[ -n "${QBO_HISTORICAL_ARCHIVE_HOST:-}" ]]; then
  browser_output="${ACCEPTANCE_BROWSER_OUTPUT:-$WORK_DIR/qbo-historical-browser-acceptance.json}"
  mkdir -p "$(dirname "$browser_output")"
  chmod 700 "$(dirname "$browser_output")"
  OM2B_SERVING_SHA="$(git -C "$ROOT_DIR" rev-parse HEAD)" \
    QBO_HISTORICAL_ACCEPTANCE=true \
    node "$ROOT_DIR/frontend/tests/real-browser-workflow.mjs" \
      "http://127.0.0.1:${published_frontend_port}" \
      "$CREDENTIAL_FILE" \
      "$RECEIPT_FILE" \
      "$browser_output" \
      qbo-historical
  chmod 600 "$browser_output"
  echo "QBO historical authenticated browser acceptance: PASS ($browser_output)"
fi

if [[ "${REVENUE_CYCLE_ACCEPTANCE:-false}" == "true" ]]; then
  browser_output="${ACCEPTANCE_BROWSER_OUTPUT:-$WORK_DIR/revenue-cycle-browser-acceptance.json}"
  mkdir -p "$(dirname "$browser_output")"
  chmod 700 "$(dirname "$browser_output")"
  OM2B_SERVING_SHA="$(git -C "$ROOT_DIR" rev-parse HEAD)" \
    REVENUE_CYCLE_ACCEPTANCE=true \
    node "$ROOT_DIR/frontend/tests/real-browser-workflow.mjs" \
      "http://127.0.0.1:${published_frontend_port}" \
      "$CREDENTIAL_FILE" \
      "$RECEIPT_FILE" \
      "$browser_output" \
      revenue-cycle
  chmod 600 "$browser_output"
  echo "Revenue-cycle authenticated browser acceptance: PASS ($browser_output)"
fi

# Host-created files are owned by the host-side user.  Stage the token through
# stdin into a file created by the actual non-root backend identity so a
# read-only bind mount preserves mode 0600 without requiring root or changing
# the application container identity.  The token value is never printed.
runtime_uid="$(compose run --rm --no-deps backend id -u)"
runtime_gid="$(compose run --rm --no-deps backend id -g)"
compose run --rm --no-deps --user 0:0 \
  --volume "$SMOKE_CUSTODY_VOLUME:/run/acceptance-custody" \
  --entrypoint /bin/sh \
  --env CUSTODY_UID="$runtime_uid" --env CUSTODY_GID="$runtime_gid" \
  backend -eu -c \
  'chown "$CUSTODY_UID:$CUSTODY_GID" /run/acceptance-custody && chmod 700 /run/acceptance-custody'
compose run --rm --no-deps --user 0:0 \
  --volume "$PRINCIPAL_CUSTODY_VOLUME:/run/acp-release" \
  --entrypoint /bin/sh \
  --env CUSTODY_UID="$runtime_uid" --env CUSTODY_GID="$runtime_gid" \
  backend -eu -c \
  'chown "$CUSTODY_UID:$CUSTODY_GID" /run/acp-release && chmod 700 /run/acp-release'
compose run --rm --no-deps --user "$runtime_uid:$runtime_gid" \
  --volume "$SMOKE_CUSTODY_VOLUME:/run/acceptance-custody" \
  --entrypoint /bin/sh backend -eu -c '
    umask 077
    cat > /run/acceptance-custody/runtime-smoke-token
    chmod 600 /run/acceptance-custody/runtime-smoke-token
    test -f /run/acceptance-custody/runtime-smoke-token
    test "$(stat -c %a /run/acceptance-custody/runtime-smoke-token)" = 600
    test -r /run/acceptance-custody/runtime-smoke-token
  ' <"$SMOKE_TOKEN_FILE"
compose run --rm --no-deps --user "$runtime_uid:$runtime_gid" \
  --volume "$SMOKE_CUSTODY_VOLUME:/run/acceptance-custody:ro" \
  --entrypoint /bin/sh backend -eu -c '
    test -r /run/acceptance-custody/runtime-smoke-token
    test "$(stat -c %a /run/acceptance-custody/runtime-smoke-token)" = 600
  '
echo "smoke token custody: PASS (container-owned volume, runtime UID/GID $runtime_uid/$runtime_gid, mode 0600, readable non-root)"

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
  echo "protected principal smoke: $smoke_check"
  compose run --rm --no-deps --no-TTY \
    --user "$runtime_uid:$runtime_gid" \
    --volume "$SMOKE_CUSTODY_VOLUME:/run/acceptance-custody:ro" \
    --env SMOKE_BASE_URL=http://frontend \
    --env SMOKE_COMPANY_ID="$smoke_company_id" \
    --env SMOKE_BRANCH_ID="$smoke_branch_id" \
    --env SMOKE_DENIED_COMPANY_ID="$smoke_denied_company_id" \
    --env SMOKE_DENIED_BRANCH_ID="$smoke_branch_id" \
    backend python /app/scripts/protected_smoke_check.py \
    --check "$smoke_check" \
    --path "$smoke_path" \
    --credential-file /run/acceptance-custody/runtime-smoke-token
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

# Exercise the actual protected principal lifecycle under the assembled
# acp_app runtime.  Principal tokens use a disposable container-owned volume;
# host directory ownership cannot affect non-root runtime access.

actor_output="$(compose run --rm --no-deps --no-TTY \
  --env SMOKE_COMPANY_ID="$smoke_company_id" \
  --volume "$PRINCIPAL_CUSTODY_VOLUME:/run/acp-release" \
  backend python -m scripts.provision_beta_release_actor \
  --company-id "$smoke_company_id" --minutes 5)"
actor_json="$(printf '%s\n' "$actor_output" | awk '/^\{/{line=$0} END{print line}')"
if [[ -z "$actor_json" ]]; then
  echo "release actor provisioning produced no metadata" >&2
  exit 1
fi
actor_session="$(printf '%s' "$actor_json" | jq -r '.session_id')"
if [[ -z "$actor_session" || "$actor_session" == "null" ]]; then
  echo "release actor provisioning did not return a session reference" >&2
  exit 1
fi

reader_output="$(compose run --rm --no-deps --no-TTY \
  --env SMOKE_COMPANY_ID="$smoke_company_id" \
  --volume "$PRINCIPAL_CUSTODY_VOLUME:/run/acp-release" \
  --entrypoint /bin/sh backend -eu -c '
    ACP_RELEASE_ACTOR_TOKEN="$(cat /run/acp-release/release-actor/access-token)"
    export ACP_RELEASE_ACTOR_TOKEN
    python -m scripts.provision_acceptance_readonly_principal \
      --company-id "$SMOKE_COMPANY_ID" \
      --minutes 5 \
      --token-output /run/acp-release/acceptance-reader/access-token
    unset ACP_RELEASE_ACTOR_TOKEN
  ')"
reader_json="$(printf '%s\n' "$reader_output" | awk '/^\{/{line=$0} END{print line}')"
reader_id="$(printf '%s' "$reader_json" | jq -r '.principal_id')"
reader_created="$(printf '%s' "$reader_json" | jq -r '.created')"
if [[ -z "$reader_id" || "$reader_id" == "null" || "$reader_created" != "true" ]]; then
  echo "acceptance reader provisioning did not create a bounded principal" >&2
  exit 1
fi

replay_output="$(compose run --rm --no-deps --no-TTY \
  --env SMOKE_COMPANY_ID="$smoke_company_id" \
  --volume "$PRINCIPAL_CUSTODY_VOLUME:/run/acp-release" \
  --entrypoint /bin/sh backend -eu -c '
    ACP_RELEASE_ACTOR_TOKEN="$(cat /run/acp-release/release-actor/access-token)"
    export ACP_RELEASE_ACTOR_TOKEN
    python -m scripts.provision_acceptance_readonly_principal \
      --company-id "$SMOKE_COMPANY_ID" \
      --minutes 5 \
      --token-output /run/acp-release/acceptance-reader/access-token
    unset ACP_RELEASE_ACTOR_TOKEN
  ')"
replay_json="$(printf '%s\n' "$replay_output" | awk '/^\{/{line=$0} END{print line}')"
if [[ "$(printf '%s' "$replay_json" | jq -r '.principal_id')" != "$reader_id" \
  || "$(printf '%s' "$replay_json" | jq -r '.created')" != "false" ]]; then
  echo "acceptance reader replay was not idempotent" >&2
  exit 1
fi
echo "acceptance reader metadata: principal=$reader_id created=true,replay=false"

compose run --rm --no-deps --no-TTY \
  --env SMOKE_COMPANY_ID="$smoke_company_id" \
  --env ACP_ACCEPTANCE_PRINCIPAL_ID="$reader_id" \
  --volume "$PRINCIPAL_CUSTODY_VOLUME:/run/acp-release" \
  --entrypoint /bin/sh backend -eu -c '
    python - <<'PY'
import asyncio
import os
from datetime import timedelta
from uuid import UUID

from app import main as application_model_registry  # noqa: F401
from app.database.session import AsyncSessionFactory
from app.database.tenant_context import set_database_tenant_context
from app.platform.auth.errors import SessionInvalidError
from app.platform.auth.services import access_token_service, authentication_service
from app.platform.permissions.authorization import authorization_service
from app.platform.service_principals.service import (
    AcceptanceServicePrincipalService,
)
from app.platform.service_principals.release_actor import utc_now


async def main() -> None:
    company_id = UUID(os.environ["SMOKE_COMPANY_ID"])
    set_database_tenant_context(company_id)
    actor_token = open(
        "/run/acp-release/release-actor/access-token", encoding="utf-8"
    ).read().strip()
    actor_claims = access_token_service.decode(actor_token)
    async with AsyncSessionFactory() as session:
        authenticated = await authentication_service.validate_access_context(
            session, actor_claims
        )
        context = await authorization_service.resolve(
            session,
            authenticated=authenticated,
            company_id=company_id,
            branch_id=None,
        )
        await session.rollback()
        async with session.begin():
            issued = await AcceptanceServicePrincipalService().issue_session(
                session,
                context=context,
                principal_id=UUID(os.environ["ACP_ACCEPTANCE_PRINCIPAL_ID"]),
                lifetime=timedelta(minutes=5),
                now=utc_now() - timedelta(minutes=10),
            )
    try:
        async with AsyncSessionFactory() as session:
            await authentication_service.validate_access_context(
                session, access_token_service.decode(issued.access_token)
            )
    except SessionInvalidError:
        print("acceptance reader expiration enforcement: PASS")
    else:
        raise SystemExit("expired acceptance reader session was accepted")


asyncio.run(main())
PY
  '

compose run --rm --no-deps --no-TTY \
  --volume "$PRINCIPAL_CUSTODY_VOLUME:/run/acp-release:ro" \
  --env SMOKE_COMPANY_ID="$smoke_company_id" \
  backend python - <<'PY'
import asyncio
import os
from pathlib import Path
from uuid import UUID

from app import main as application_model_registry  # noqa: F401
from app.database.session import AsyncSessionFactory
from app.database.tenant_context import set_database_tenant_context
from app.platform.auth.services import access_token_service, authentication_service


async def main() -> None:
    set_database_tenant_context(UUID(os.environ["SMOKE_COMPANY_ID"]))
    token = Path(
        "/run/acp-release/acceptance-reader/access-token"
    ).read_text().strip()
    claims = access_token_service.decode(token)
    async with AsyncSessionFactory() as session:
        await authentication_service.validate_access_context(session, claims)
    print("acceptance reader token authentication: PASS")


asyncio.run(main())
PY

for smoke_check in authentication authorization tenant-isolation; do
  case "$smoke_check" in
    authentication)
      smoke_path=/api/v1/authorization/companies
      ;;
    authorization|tenant-isolation)
      smoke_path=/api/v1/workforce/employees
      ;;
  esac
  echo "acceptance reader smoke: $smoke_check"
  compose run --rm --no-deps --no-TTY \
    --volume "$PRINCIPAL_CUSTODY_VOLUME:/run/acp-release:ro" \
    --env SMOKE_BASE_URL=http://frontend \
    --env SMOKE_COMPANY_ID="$smoke_company_id" \
    --env SMOKE_BRANCH_ID="$smoke_branch_id" \
    --env SMOKE_DENIED_COMPANY_ID="$smoke_denied_company_id" \
    --env SMOKE_DENIED_BRANCH_ID="$smoke_branch_id" \
    backend python /app/scripts/protected_smoke_check.py \
    --check "$smoke_check" \
    --path "$smoke_path" \
    --credential-file /run/acp-release/acceptance-reader/access-token
done

revoke_reader_output="$(compose run --rm --no-deps --no-TTY \
  --env SMOKE_COMPANY_ID="$smoke_company_id" \
  --env ACP_ACCEPTANCE_PRINCIPAL_ID="$reader_id" \
  --volume "$PRINCIPAL_CUSTODY_VOLUME:/run/acp-release" \
  --entrypoint /bin/sh backend -eu -c '
    ACP_RELEASE_ACTOR_TOKEN="$(cat /run/acp-release/release-actor/access-token)"
    export ACP_RELEASE_ACTOR_TOKEN
    python -m scripts.revoke_acceptance_readonly_principal \
      --company-id "$SMOKE_COMPANY_ID" \
      --principal-id "$ACP_ACCEPTANCE_PRINCIPAL_ID"
    unset ACP_RELEASE_ACTOR_TOKEN
  ')"
if ! printf '%s\n' "$revoke_reader_output" | grep -q '"state": "revoked"'; then
  echo "acceptance reader revocation did not complete" >&2
  exit 1
fi

compose run --rm --no-deps --no-TTY \
  --env SMOKE_COMPANY_ID="$smoke_company_id" \
  --volume "$PRINCIPAL_CUSTODY_VOLUME:/run/acp-release" \
  backend python -m scripts.revoke_beta_release_actor \
  --company-id "$smoke_company_id"
echo "protected principal lifecycle: PASS (provision, issue, replay, smoke, revoke, cleanup)"

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

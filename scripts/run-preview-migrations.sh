#!/usr/bin/env bash
set -euo pipefail

# Run only the governed Preview migration step.  The API URL is deliberately
# not accepted as a migration credential and no URL is printed.
: "${MIGRATION_DATABASE_URL:?MIGRATION_DATABASE_URL is required}"
: "${PREVIEW_RELEASE:?PREVIEW_RELEASE must be true}"
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [[ "$PREVIEW_RELEASE" != "true" ]]; then
  echo "Preview migration requires PREVIEW_RELEASE=true" >&2
  exit 2
fi

database_user="$(${PYTHON:-python3} - "$MIGRATION_DATABASE_URL" <<'PY'
import sys
from urllib.parse import urlsplit

url = urlsplit(sys.argv[1])
print(url.username or "")
PY
)"
if [[ "$database_user" != "acp_migrate" ]]; then
  echo "MIGRATION_DATABASE_URL must use acp_migrate" >&2
  exit 2
fi

unset DATABASE_URL
export DATABASE_URL="$MIGRATION_DATABASE_URL"
export PYTHONPATH="$root/backend${PYTHONPATH:+:$PYTHONPATH}"
cd "$root/backend"
exec "${PYTHON:-python3}" -m alembic upgrade head

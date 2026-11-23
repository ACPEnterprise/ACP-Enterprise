#!/bin/sh
set -eu

backup_root=${BACKUP_ROOT:-/opt/acp-enterprise/backups/scheduled}
postgres_container=${PREVIEW_POSTGRES_CONTAINER:-acp-enterprise-postgres}
backup_database_user=${PREVIEW_BACKUP_DATABASE_USER:-acp_backup}
backup_password_file=${PREVIEW_BACKUP_DATABASE_PASSWORD_FILE:-/run/secrets/acp_backup_password}

test -n "$backup_database_user"
test -n "$backup_password_file"

umask 077
install -d -m 700 "$backup_root"

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
final_dump=$backup_root/preview-$timestamp.dump
temporary_dump=$(mktemp "$backup_root/.preview-$timestamp.XXXXXX.dump")
trap 'rm -f "$temporary_dump" "$temporary_dump.sha256"' EXIT HUP INT TERM

docker inspect --format '{{.State.Running}}' "$postgres_container" | grep -qx true
docker exec "$postgres_container" \
  env "BACKUP_DATABASE_USER=$backup_database_user" \
  "BACKUP_DATABASE_PASSWORD_FILE=$backup_password_file" \
  sh -eu -c 'test -r "$BACKUP_DATABASE_PASSWORD_FILE"; PGPASSWORD=$(cat "$BACKUP_DATABASE_PASSWORD_FILE"); export PGPASSWORD; pg_dump -U "$BACKUP_DATABASE_USER" -d "$POSTGRES_DB" --format=custom' \
  >"$temporary_dump"

test -s "$temporary_dump"
docker exec -i "$postgres_container" \
  pg_restore --list <"$temporary_dump" >/dev/null
chmod 600 "$temporary_dump"
checksum=$(sha256sum "$temporary_dump" | awk '{print $1}')
printf '%s  %s\n' "$checksum" "$(basename "$final_dump")" >"$temporary_dump.sha256"
chmod 600 "$temporary_dump.sha256"

mv "$temporary_dump" "$final_dump"
mv "$temporary_dump.sha256" "$final_dump.sha256"
trap - EXIT HUP INT TERM

echo "preview_backup=$final_dump"
echo "preview_backup_sha256=$final_dump.sha256"

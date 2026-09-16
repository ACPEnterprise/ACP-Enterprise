#!/bin/sh
set -eu

backup_root=${BACKUP_ROOT:-/opt/acp-enterprise/backups/scheduled}
postgres_container=${PREVIEW_POSTGRES_CONTAINER:-acp-enterprise-postgres}

umask 077
install -d -m 700 "$backup_root"

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
final_dump=$backup_root/preview-$timestamp.dump
temporary_dump=$(mktemp "$backup_root/.preview-$timestamp.XXXXXX.dump")
trap 'rm -f "$temporary_dump" "$temporary_dump.sha256"' EXIT HUP INT TERM

docker inspect --format '{{.State.Running}}' "$postgres_container" | grep -qx true
docker exec "$postgres_container" \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
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

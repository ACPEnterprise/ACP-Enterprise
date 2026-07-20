#!/bin/sh
set -eu

environment_file=${1:-.env.preview}
compose_file=${COMPOSE_FILE:-docker-compose.preview.yml}
preview_url=${PREVIEW_URL:-http://127.0.0.1:8080}

if [ ! -f "$environment_file" ]; then
  echo "Missing preview environment file: $environment_file" >&2
  exit 1
fi

compose() {
  docker compose --env-file "$environment_file" -f "$compose_file" "$@"
}

require_healthy() {
  service=$1
  attempts=0
  while [ "$attempts" -lt 30 ]; do
    container_id=$(compose ps -q "$service")
    if [ -n "$container_id" ]; then
      health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")
      if [ "$health" = "healthy" ]; then
        echo "$service: healthy"
        return
      fi
    else
      health="not running"
    fi
    attempts=$((attempts + 1))
    sleep 2
  done
  echo "Service did not become healthy: $service ($health)" >&2
  exit 1
}

require_healthy postgres
require_healthy redis
require_healthy backend
require_healthy frontend

compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null
compose exec -T redis redis-cli ping | grep -qx PONG

curl --fail --silent --show-error "$preview_url/backend-health" \
  | python3 -c 'import json,sys; payload=json.load(sys.stdin); assert payload["status"] == "healthy"'
curl --fail --silent --show-error "$preview_url/healthz" >/dev/null
curl --fail --silent --show-error "$preview_url/mission-control" >/dev/null
curl --fail --silent --show-error "$preview_url/customers" >/dev/null

current_revision=$(compose exec -T backend alembic current)
printf '%s\n' "$current_revision" | grep -q '(head)'

echo "Backend health: healthy"
echo "Frontend and direct routes: reachable"
echo "Database migration state: current at head"
echo "Preview verification completed successfully."

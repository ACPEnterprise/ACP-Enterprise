#!/bin/sh
set -eu

beta_url=${BETA_URL:-https://beta.twelve-hats.com}
start_at=${SMOKE_START_AT:-2000-01-01T00:00:00Z}
end_at=${SMOKE_END_AT:-2000-01-02T00:00:00Z}
config_file=$(mktemp)
body_file=$(mktemp)
trap 'rm -f "$config_file" "$body_file"' EXIT HUP INT TERM
chmod 600 "$config_file" "$body_file"

status() {
  curl --silent --show-error --max-time 20 --output "$body_file" \
    --write-out '%{http_code}' "$1"
}

require_status() {
  expected=$1
  url=$2
  actual=$(status "$url")
  if [ "$actual" != "$expected" ]; then
    echo "Unexpected status for $url: expected $expected, received $actual." >&2
    exit 1
  fi
}

authenticated_status() {
  token_file=$1
  url=$2
  mode=$(stat -c '%a' "$token_file")
  if [ "$mode" != "600" ]; then
    echo "Token reference must be mode 0600: $token_file" >&2
    exit 1
  fi
  token=$(tr -d '\r\n' <"$token_file")
  test -n "$token"
  printf 'header = "Authorization: Bearer %s"\n' "$token" >"$config_file"
  curl --silent --show-error --max-time 20 --config "$config_file" \
    --output "$body_file" --write-out '%{http_code}' "$url"
  : >"$config_file"
  unset token
}

for route in payroll scheduling dispatch; do
  require_status 200 "$beta_url/$route"
done

payroll_url=$beta_url/api/v1/payroll/operations/summary
scheduling_url="$beta_url/api/v1/scheduling/appointments?start_at=$start_at&end_at=$end_at"
dispatch_url="$beta_url/api/v1/dispatch/board?start_at=$start_at&end_at=$end_at"
my_day_url=$beta_url/api/v1/employee-operations/me/day

for url in "$payroll_url" "$scheduling_url" "$dispatch_url" "$my_day_url"; do
  require_status 401 "$url"
done

blocked=0
for contract in \
  "PAYROLL_TOKEN_FILE|$payroll_url|payroll" \
  "DISPATCH_TOKEN_FILE|$scheduling_url|scheduling" \
  "DISPATCH_TOKEN_FILE|$dispatch_url|dispatch" \
  "EMPLOYEE_TOKEN_FILE|$my_day_url|my_day"
do
  variable=${contract%%|*}
  remainder=${contract#*|}
  url=${remainder%|*}
  label=${contract##*|}
  eval "token_file=\${$variable:-}"
  if [ -z "$token_file" ]; then
    echo "$label=BLOCKED_SANCTIONED_TOKEN_REQUIRED"
    blocked=1
    continue
  fi
  actual=$(authenticated_status "$token_file" "$url")
  case "$actual" in
    200) echo "$label=PASS" ;;
    401|403) echo "$label=AUTHORIZATION_BLOCKED_HTTP_$actual"; blocked=1 ;;
    4??) echo "$label=DOMAIN_BLOCKED_HTTP_$actual"; blocked=1 ;;
    *) echo "$label=RUNTIME_FAILURE_HTTP_$actual" >&2; exit 1 ;;
  esac
done

echo "public_routes=PASS"
echo "unauthenticated_apis=FAIL_CLOSED"
if [ "$blocked" -ne 0 ]; then
  exit 2
fi
echo "beta_payroll_dispatch_cutover_smoke=PASS"

#!/bin/sh
set -eu

preview_url=https://preview.allcountyhomeservices.com
beta_url=https://beta.twelve-hats.com
expected_beta_ipv4=${EXPECTED_BETA_IPV4:-162.243.234.193}

temporary_headers=$(mktemp)
trap 'rm -f "$temporary_headers"' EXIT HUP INT TERM

require_status() {
  expected=$1
  url=$2
  actual=$(curl --silent --show-error --max-time 15 --output /dev/null --write-out '%{http_code}' "$url")
  if [ "$actual" != "$expected" ]; then
    echo "Unexpected status for $url: expected $expected, received $actual" >&2
    exit 1
  fi
}

require_header() {
  name=$1
  expected=$2
  if ! grep -Eiq "^${name}:[[:space:]]*${expected}[[:space:]]*\r?$" "$temporary_headers"; then
    echo "Missing or unsafe $name response header." >&2
    exit 1
  fi
}

beta_ipv4=$(dig +short A beta.twelve-hats.com | sort -u)
if [ "$beta_ipv4" != "$expected_beta_ipv4" ]; then
  echo "beta.twelve-hats.com must resolve only to $expected_beta_ipv4; observed: ${beta_ipv4:-UNRESOLVED}" >&2
  exit 1
fi

for base_url in "$preview_url" "$beta_url"; do
  require_status 200 "$base_url/"
  require_status 200 "$base_url/healthz"
  require_status 200 "$base_url/backend-health"
  require_status 200 "$base_url/employees"
  require_status 401 "$base_url/api/v1/auth/session"
  curl --silent --show-error --max-time 15 --head "$base_url/" >"$temporary_headers"
  require_header 'strict-transport-security' 'max-age=(31536000|[4-9][0-9]{7,}|[1-9][0-9]{8,});[[:space:]]*includeSubDomains'
  require_header 'x-content-type-options' 'nosniff'
  require_header 'x-frame-options' 'DENY'
  require_header 'referrer-policy' 'strict-origin-when-cross-origin'
  require_header 'permissions-policy' '.+'
  require_header 'content-security-policy' '.+'
done

require_status 404 "$beta_url/mission-control"
require_status 404 "$beta_url/engineering"
require_status 404 "$beta_url/api/v1/worker-transport/sessions/challenge"

cors_headers=$(curl --silent --show-error --max-time 15 --request OPTIONS \
  --header 'Origin: https://beta.twelve-hats.com' \
  --header 'Access-Control-Request-Method: POST' \
  --dump-header - --output /dev/null \
  "$beta_url/api/v1/auth/login")
printf '%s\n' "$cors_headers" | grep -iq '^access-control-allow-origin: https://beta.twelve-hats.com'
printf '%s\n' "$cors_headers" | grep -iq '^access-control-allow-credentials: true'

hostile_cors_headers=$(curl --silent --show-error --max-time 15 --request OPTIONS \
  --header 'Origin: https://attacker.invalid' \
  --header 'Access-Control-Request-Method: POST' \
  --dump-header - --output /dev/null \
  "$beta_url/api/v1/auth/login")
if printf '%s\n' "$hostile_cors_headers" | grep -Eiq \
  '^access-control-allow-origin:[[:space:]]*(\*|https://attacker\.invalid)[[:space:]]*\r?$'; then
  echo "Beta edge accepted an untrusted CORS origin." >&2
  exit 1
fi

certificate=$(mktemp)
trap 'rm -f "$temporary_headers" "$certificate"' EXIT HUP INT TERM
echo | openssl s_client -servername beta.twelve-hats.com \
  -connect beta.twelve-hats.com:443 2>/dev/null \
  | openssl x509 -out "$certificate"
openssl x509 -in "$certificate" -noout -checkend 604800 >/dev/null
certificate_expiry=$(openssl x509 -in "$certificate" -noout -enddate | cut -d= -f2-)
test -n "$certificate_expiry"

echo "Preview and Twelve Hats Beta connectivity accepted."
echo "beta_ipv4=$beta_ipv4"
echo "beta_certificate_expiry=$certificate_expiry"

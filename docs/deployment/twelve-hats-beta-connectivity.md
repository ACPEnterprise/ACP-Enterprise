# Twelve Hats Beta connectivity

Twelve Hats Beta reuses the existing Preview application runtime without renaming,
redirecting, or removing `preview.allcountyhomeservices.com`. All County Plumbing &
Leak remains the tenant and owns its business data. `beta.twelve-hats.com` is the
Twelve Hats-owned public beta entry point. This packet does not touch
`app.twelve-hats.com` and creates no Production resource.

## Current evidence — 2026-09-17

- Preview and Beta resolve to `162.243.234.193` and terminate valid Let's Encrypt TLS
  in Caddy before proxying to loopback frontend Nginx on port 8080. The Beta
  certificate is valid through 2026-12-15 and Caddy is receiving ACME renewal-window
  updates.
- Frontend, backend, PostgreSQL and Redis containers are healthy. The backend health
  projection reports database, schema and Redis healthy and is identical through both
  hostnames. The isolated Mission Control API and web services are also healthy.
- The `twelve-hats.com` zone uses GoDaddy nameservers. The accepted record is exactly
  `beta A 162.243.234.193`; do not create or change `app.twelve-hats.com`.
- The host Caddy service is active and automatically owns certificate issuance and
  renewal for both hostnames.
- Only ports 22, 80 and 443 are host-firewall accessible. SSH is currently permitted
  from anywhere, which is a hardening follow-up; database, Redis and backend have no
  public host ports.
- Root disk utilization is 82% with approximately 14 GiB available. Treat 85% as a
  warning and 90% as a blocker; remove only classified disposable build/cache data,
  never databases, evidence, backups or rollback packages.
- No cookie domain migration exists. Web refresh tokens are held in per-origin
  `sessionStorage`; bearer access tokens are in memory. A user visiting the Beta host
  must sign in once there. Mobile uses OS secure storage and continues to call the
  preserved Preview API.
- Public `/`, `/healthz`, `/backend-health`, and SPA direct routes work on Preview.
  `/api/v1/auth/session` fails closed with 401 when unauthenticated.
- The deployed frontend emits one browser security-header policy, and exact
  activation/reset pages return `Referrer-Policy: no-referrer` without retaining their
  requests in Caddy or Nginx access logs.
- Preview Mission Control is healthy and its unauthenticated API fails closed with
  401. Beta deliberately returns 404 for Mission Control, engineering APIs/assets and
  worker transport.
- The daily restricted database backup timer and five-minute local Beta connectivity
  monitor are enabled. The latest scheduled dump is mode 0600, checksum-valid and
  readable by `pg_restore --list`.

## Accepted activation and ongoing release gate

1. Preserve the dual-host `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` configuration in
   every Preview release. Keep
   identity activation and both QBO callback origins on Preview until their provider
   registrations are separately migrated.
2. Before changing Caddy, run `caddy validate --config /etc/caddy/Caddyfile` and save
   the previous file mode-0600 under the existing configuration-backup boundary.
3. Preserve the accepted GoDaddy DNS record:

   `beta  A  162.243.234.193  TTL 600`

4. Require authoritative and public resolution and a valid automatically managed Beta
   certificate. Do not use a temporary certificate or disable TLS verification.
5. Run `scripts/verify-beta-connectivity.sh`. Then perform an authenticated browser
   pass using a sanctioned Beta employee/owner identity and verify Company/Branch,
   direct-route refresh, logout/login, session refresh and authorization changes.
6. Keep Preview live throughout the beta observation window. Do not redirect Preview
   to Beta; that would discard origin-scoped browser sessions and could break existing
   Mobile/API clients and registered OAuth callbacks.

## Mobile and endpoint compatibility

Existing TestFlight build 2 and protected source build 3 are compiled and exact-pinned
to `https://preview.allcountyhomeservices.com`; Expo updates are disabled. They require
no change while Preview remains live. Pointing Mobile itself at
`https://beta.twelve-hats.com` requires a successor build after DNS/TLS/health are
accepted and Mobile's exact Preview-host guard and release manifests are reconciled.
The bundle identifier and Apple signing identity do not need to change.

## Support and privacy URLs

Reserved targets are `https://beta.twelve-hats.com/support` and
`https://beta.twelve-hats.com/privacy`. The SPA currently has no approved public
content for either route; a generic SPA 200 is not legal/support readiness. Publish
owner/legal-approved static content and verify direct unauthenticated 200 responses,
content ownership, version/effective date and contact path before using these URLs in
App Store Connect. Do not invent policy or contact language in infrastructure.

## Monitoring without provider spend

The root-owned systemd oneshot/timer runs the repository verification every five
minutes. Results go to journald and a nonzero exit is
visible through `systemctl --failed` and `journalctl`; this is local detection, not
paging. The verifier requires exact DNS, HTTPS redirects, route health, identical
Preview/Beta backend projections, one edge security-header policy, trusted and
untrusted CORS behavior, internal-route isolation, and at least 14 days of TLS
validity. Continue checking container health, Caddy status and disk utilization as
separate host-level signals. A named human and external alert delivery remain required
for unattended beta operations.

Set `REQUIRE_PUBLIC_METADATA=1` only after approved support and privacy content is
published. That release gate rejects either URL while it still returns the generic
application shell.

Installed units originate from the templates
`twelve-hats-beta-connectivity-monitor.service.example` and
`twelve-hats-beta-connectivity-monitor.timer.example`. Keep the service's
`WorkingDirectory` and `ExecStart` at the immutable deployed release or controlled
`current` symlink and verify the unit after each release. The timer must remain enabled
only while DNS/TLS activation is intended because an absent Beta record fails closed.

## Rollback

1. Remove the Beta DNS record; do not alter Preview DNS.
2. Restore the backed-up Caddyfile, validate it, and reload Caddy.
3. Restore the prior Preview environment values and recreate only backend/worker
   services if necessary; do not delete volumes or downgrade schema.
4. Re-run Preview verification and confirm Mobile build 2/3 still reaches the original
   endpoint.
5. Preserve Caddy/container logs and the failed verification output. Certificate
   material can expire naturally; do not revoke Preview's certificate.

Rollback never changes `app.twelve-hats.com`, the Apple bundle ID, customer data,
database volumes, or Production.

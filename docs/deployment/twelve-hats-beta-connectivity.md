# Twelve Hats Beta connectivity

Twelve Hats Beta reuses the existing Preview application runtime without renaming,
redirecting, or removing `preview.allcountyhomeservices.com`. All County Plumbing &
Leak remains the tenant and owns its business data. `beta.twelve-hats.com` is the
Twelve Hats-owned public beta entry point. This packet does not touch
`app.twelve-hats.com` and creates no Production resource.

## Current evidence — 2026-09-16

- Preview resolves to `162.243.234.193` and terminates valid Let's Encrypt TLS in
  Caddy before proxying to loopback frontend Nginx on port 8080.
- Frontend, backend, PostgreSQL and Redis containers are healthy. The backend health
  projection reports database, schema and Redis healthy.
- `beta.twelve-hats.com` is absent from DNS. The `twelve-hats.com` zone uses GoDaddy
  nameservers, so the exact external action is an `A` record named `beta`, value
  `162.243.234.193`, TTL 600. Do not create or change `app.twelve-hats.com`.
- The host Caddy service is active and automatically owns certificate issuance and
  renewal. Its current Preview certificate is valid through 2026-10-18.
- Only ports 22, 80 and 443 are host-firewall accessible. SSH is currently permitted
  from anywhere, which is a hardening follow-up; database, Redis and backend have no
  public host ports.
- Root disk utilization is 80% with approximately 16 GiB available. Treat 85% as a
  warning and 90% as a blocker; remove only classified disposable build/cache data,
  never databases, evidence, backups or rollback packages.
- No cookie domain migration exists. Web refresh tokens are held in per-origin
  `sessionStorage`; bearer access tokens are in memory. A user visiting the Beta host
  must sign in once there. Mobile uses OS secure storage and continues to call the
  preserved Preview API.
- Public `/`, `/healthz`, `/backend-health`, and SPA direct routes work on Preview.
  `/api/v1/auth/session` fails closed with 401 when unauthenticated.
- The deployed frontend currently duplicates browser security headers on proxied API
  responses because both FastAPI and Nginx add them. This candidate hides upstream
  copies at Nginx and emits the edge policy once; deploy with the next reviewed
  frontend image rather than editing a running container.
- Preview Mission Control is currently unavailable: its web container restarts because
  upstream `backend` is unresolved, and its API reports an application/schema-head
  mismatch. This does not affect the healthy tenant application, but it must be owned
  as a separate internal-runtime repair. Beta deliberately returns 404 for Mission
  Control, engineering APIs/assets and worker transport.

## Safe activation order

1. Integrate this packet and deploy the dual-host `ALLOWED_HOSTS` and
   `CORS_ALLOWED_ORIGINS` configuration to the existing Preview backend. Keep
   identity activation and both QBO callback origins on Preview until their provider
   registrations are separately migrated.
2. Install the reviewed Caddyfile and run `caddy validate --config /etc/caddy/Caddyfile`.
   Save the previous file mode-0600 under the existing configuration-backup boundary.
3. At GoDaddy DNS, create only:

   `beta  A  162.243.234.193  TTL 600`

4. Wait for authoritative and public resolution. Caddy then obtains the Beta
   certificate automatically. Do not use a temporary certificate or disable TLS
   verification.
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

Install a root-owned systemd oneshot/timer that runs the repository verification every
five minutes after Beta DNS activation. Results go to journald and a nonzero exit is
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

Templates are provided as
`twelve-hats-beta-connectivity-monitor.service.example` and
`twelve-hats-beta-connectivity-monitor.timer.example`. Point the service's
`WorkingDirectory` and `ExecStart` at the immutable deployed release or controlled
`current` symlink, run the verifier manually once, then enable the timer. Do not enable
it before DNS/TLS activation because an intentionally absent Beta record must fail.

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

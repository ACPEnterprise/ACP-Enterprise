# COSMIC Beta platform connectivity — Enterprise Release handoff

## Candidate

- Starting protected authority: `5f7a45118885a38e5faa4fcfcf98dd395d3ea7ea`
- Branch: `work/om1c-cosmic-beta-connectivity-1`
- Scope: preserve the existing Preview hostname while making the same Beta runtime
  safe to expose at `beta.twelve-hats.com`.
- Excluded: `app.twelve-hats.com`, Production deployment, Apple signing, customer
  data mutation, provider purchases and permanent All County-owned platform assets.

## Runtime checkpoint

The existing Preview backend and identity-delivery worker have already been restarted
with exact trusted-host and CORS allowlists for both Preview and Beta. The prior
runtime environment is preserved mode-0600 at:

`/opt/acp-enterprise/config-backups/cosmic-beta-connectivity-20260916/.env.preview.before-beta-hosts`

Preview remained healthy after the restart. Preview and Beta origins receive exact
CORS responses; an unapproved origin fails closed. The future Beta host was exercised
internally through the current frontend for root, health, backend health, direct SPA
routing and unauthenticated-session rejection.

No public Beta DNS record or certificate exists yet. The candidate Caddyfile validates,
but it has not been installed or reloaded. `app.twelve-hats.com` was not changed.

## Required activation gate

The domain owner must create this single GoDaddy record:

`beta  A  162.243.234.193  TTL 600`

Enterprise Release then installs the reviewed Caddy candidate with a mode-0600 backup,
validates and reloads Caddy, waits for public DNS and automatic TLS issuance, and runs:

```sh
scripts/verify-beta-connectivity.sh
```

An authenticated sanctioned-user pass must follow. Keep Preview live and do not
redirect it: browser sessions are origin-scoped, current Mobile builds call Preview,
and identity/QBO provider callbacks remain registered there.

## Evidence and remaining blockers

- Preview application, backend, PostgreSQL and Redis health passed.
- Exact Beta and Preview CORS passed; unapproved-origin rejection passed.
- Caddy candidate validation and frontend Nginx syntax validation passed.
- Contract and network-exposure tests passed.
- Public Beta verification is blocked only by domain-owner DNS action and subsequent
  controlled Caddy/TLS activation.
- `/support` and `/privacy` do not contain approved public content. Owner/legal content
  is required before these may be used as App Store support/privacy URLs.
- Preview Mission Control remains independently unavailable because its web upstream
  does not resolve and its API schema head does not match. Beta fails these internal
  paths closed rather than exposing or masking that defect.
- Existing TestFlight builds need no change while Preview remains available. Changing
  the Mobile API origin to Beta requires a successor build because the endpoint is
  compiled and exact-pinned.
- Root disk was 80% utilized and SSH remains publicly reachable on port 22. These are
  operational hardening items, not reasons to mutate data or silently clean storage.
- The supplied timer provides local five-minute failure detection only. A named human
  and an external alert channel remain required for unattended response.

## Rollback

Remove only the Beta DNS record, restore and validate the backed-up Caddyfile, restore
the saved Preview environment if needed, and recreate only backend/worker services.
Do not delete volumes, downgrade schema, change Preview DNS or touch Production.

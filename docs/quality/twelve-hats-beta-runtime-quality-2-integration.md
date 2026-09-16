# Twelve Hats Beta runtime quality 2 — Enterprise Release handoff

## Authority and public acceptance

- Starting protected authority: `63e4ac863763e00a3090e172a43fc32e5feb17da`
- Prior connectivity candidate: PR #386, integrated by `e4947b66f5ef3bb6f6e095fd42d29ce14fa650d2`
- Beta internal-surface hotfix: PR #389, integrated by `63e4ac863763e00a3090e172a43fc32e5feb17da`
- Public DNS: `beta.twelve-hats.com` resolves only to `162.243.234.193`
- TLS: valid through 2026-12-15
- Public connectivity verifier: passed

Preview and Beta root, health, backend health, direct Employee route and
unauthenticated-session behavior passed. Their backend health projections are
identical. HTTP redirects preserve each hostname and enforce HTTPS. Browser security
headers occur once. Beta accepts its exact CORS origin with credentials and rejects an
untrusted origin without an allow-origin response. Mission Control, engineering and
worker-transport surfaces return 404 on Beta.

## Verifier repair

The original verifier could pass while Preview and Beta served different backend
releases, while edge headers were duplicated, while untrusted CORS was accepted, when
HTTP redirects were wrong, or when the certificate was near expiry. This candidate
adds deterministic gates for all five conditions.

Approved support/privacy content remains a human/legal gate. Setting
`REQUIRE_PUBLIC_METADATA=1` makes the verifier reject `/support` or `/privacy` while
either is still the generic application shell. The gate currently fails truthfully at
`/support`; it must not be enabled as a timer environment value until approved content
is deployed.

## Runtime drift requiring controlled Release repair

The tenant application is healthy. These separate containers are not:

| Runtime | Observed state | Exact evidence | Required Release action |
| --- | --- | --- | --- |
| Mission Control web | restart loop | Nginx resolves upstream `backend`, but the isolated network exposes the API only as `acp-enterprise-mission-control-api` | Recreate the coherent Mission Control web/API pair using the accepted dedicated artifact and an explicit web-to-API network alias; do not attach it broadly for convenience. |
| Mission Control API | unhealthy, 621+ failed checks | Deployed API version `0b74c765...` and platform fingerprint `f0c90b...` are stale; tenant backend is `e4947b66...` with fingerprint `d7d2db...`; health is 503 despite database/Redis connectivity | Replace the complete isolated API/web release from current protected authority using the migration, release-consistency and rollback gates. Do not edit fingerprints to force agreement. |
| Phone7 API | restart loop | PostgreSQL rejects the configured `acp_enterprise` credential | Determine whether this legacy runtime is still authoritative. If active, rotate/reinject its credential through the approved secret boundary and recreate it; if superseded, preserve logs/evidence and retire it through controlled Release cleanup. |

No runtime container was restarted, reconfigured or deleted during this sweep.

## UI friction ledger

| Screen | Task | Friction | Severity | Surface | Safe repair |
| --- | --- | --- | --- | --- | --- |
| `/support` | obtain Beta support | Returns the generic authenticated application shell, not support content | `BLOCKS_WORK` for App Store metadata | desktop/mobile | Human/legal-approved content required |
| `/privacy` | read Beta privacy policy | Returns the generic application shell, not an approved policy | `BLOCKS_WORK` for App Store metadata | desktop/mobile | Human/legal-approved content required |
| Preview `/mission-control` | operate engineering runtime | Returns 502 because the web and API release is incoherent | `BLOCKS_WORK` | desktop | Controlled coherent Release replacement required |

## Qualification

- Public verifier, normal mode: passed
- Public metadata gate: failed as designed on generic `/support`
- Platform connectivity and network exposure: 9 tests passed
- Shell syntax, Ruff, formatting and diff checks: required before integration
- Production and `app.twelve-hats.com`: untouched


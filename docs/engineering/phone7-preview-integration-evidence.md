# PHONE.7 Preview integration evidence

Recorded 2026-07-31 against the production-like Preview environment. Production
was not targeted or accessed.

## Release boundary

- Release: `ae55168d6d090f3e418920bf5d3d519edf27284d`.
- Rollback artifact: `/opt/acp-enterprise/backups/phone7-pre-ae55168`.
- Schema head: `h3d5f7a9c264`.
- PHONE.7 API and web containers run with `restart: unless-stopped` on an
  isolated Preview network. The existing Customer Migration backend and
  frontend containers were not replaced.
- The persistent authenticated worker runs release `ae55168`, is healthy, and
  connects to the integrated PHONE.7 API.

## Phone workflow rehearsal

- Engineering Command: `292a683d-ad91-42fa-ae8a-19a67467d960`.
- Controlled offer: `476e68b8-785a-4e63-a401-a049a9e58679`.
- An authenticated owner session created the bounded inspection command.
- The command appeared in the owner approval queue and exact-evidence approval
  changed it to approved.
- The authenticated SSE stream observed `owner_request` followed by
  `worker_acknowledgement`.
- The worker acquired the bounded offer, returned one non-mutating result, and
  published running then completed runtime events with 100 percent progress.
- Mission Control created one completed notification. The owner acknowledged it
  through the version-checked authenticated endpoint.
- Reconnection using the owner-request event ID replayed only later ordered
  events; the original event was not duplicated.

## Recovery and deployment

- Restarting the worker increased authenticated sessions from 43 to 44.
- The worker returned healthy with an empty recovery journal.
- Both the isolated PHONE.7 health path and the existing public Preview health
  path reported connected PostgreSQL and Redis.
- The additive migration and PHONE.7 services deployed successfully; deployment
  rollback includes the prior container definitions and a restricted compressed
  Preview database dump.
- The synthetic rehearsal workspace and temporary authentication/replay files
  were removed.

No credential, access token, private key, environment secret, raw log, Preview
data, or repository content is included in this evidence.

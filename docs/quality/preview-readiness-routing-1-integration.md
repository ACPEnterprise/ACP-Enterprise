# Preview readiness routing 1 — Enterprise Release handoff

## Candidate

- Starting protected authority: `b527d75eecb2d271a29bcb0bacb9e1b16b33784b`
- Scope: expose the already-authoritative platform liveness/readiness projections
  through Preview and Twelve Hats Beta.
- Backend/schema/authorization impact: none.
- Deployment performed: no.

## Proven defect

The platform architecture and resilience runbook require `/health/live` and
`/health/ready`. FastAPI serves both correctly, but frontend Nginx routed them through
SPA fallback. Both public hostnames therefore returned HTML 200 even if the backend
readiness contract was never reached. Monitoring could not distinguish a live process
from a release blocked by database, schema or Redis readiness.

## Repair

Frontend Nginx now proxies only the two exact health paths to their corresponding
backend routes. The existing `/healthz` frontend liveness and `/backend-health`
compatibility projection remain unchanged. The Beta verifier now requires:

- `/health/live` HTTP 200 with `status=alive`;
- `/health/ready` HTTP 200 with aggregate `state=HEALTHY`;
- the same contract through Preview and Beta.

Health access logging remains disabled at Nginx to avoid five-minute monitor noise.

## Acceptance

After deployment, run `scripts/verify-beta-connectivity.sh` and confirm both health
paths return JSON rather than the SPA. Rehearse a dependency-not-ready state only in an
isolated environment; do not interrupt Preview merely to prove a negative state.

## Qualification

- Focused connectivity contracts: 11 tests passed; Nginx and shell syntax passed.
- Production and `app.twelve-hats.com`: untouched.

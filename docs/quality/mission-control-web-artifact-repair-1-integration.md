# Mission Control web artifact repair 1 — Enterprise packet

## Candidate

- Program: `MISSION.CONTROL.WEB.ARTIFACT.REPAIR.1`
- Starting authority: `5ee0dd237ed052864c951950c1836b23f4a063b3`
- Reconciled authority: `a7ddd8361fa8d2db08cc84c96e0343508bbe239c`
- Implementation commit: `59ae8e8af0c7896990acc707d771f5120f2d0094`
- Branch: `work/mission-control-web-artifact-repair-1`
- Schema change: none
- Preview deployment performed: no
- Production operation performed: no

The locally built candidate contains 86 files and has the deterministic
artifact identity:

`96ef694bb8b190eb3c8970162c979648efee972eb2eada2bd9fbfdf05c33ac52`

This digest is the verifier's ordered digest of relative path, NUL separator,
file bytes, and NUL separator for every emitted file. Enterprise must rebuild
after protected integration and use the digest produced by that integrated
source as the release identity; it must not assume the pre-integration digest
when protected authority changes.

## Defect and repair

Current Preview `/engineering` serves an older artifact whose entry point is
`/assets/index-CVQ1jOQF.js`. `/mission-assets/` returns HTML rather than a
Mission Control static bundle. This violates the committed Caddy and
architecture contract requiring Mission Control assets under
`/mission-assets/`.

`frontend/Dockerfile.mission-control` now provides a dedicated, reproducible
build. It fixes `VITE_BASE_PATH=/mission-assets/` while retaining the existing
same-origin `VITE_API_BASE_URL=/`. The primary `frontend/Dockerfile` and its `/`
base remain unchanged. The artifact verifier proves that every emitted
JavaScript, CSS, and SVG reference is present under `/mission-assets/`, rejects
source maps and protected patterns, and emits the artifact digest.

The Preview verifier now requires `/engineering` and `/mission-control` to
resolve to the same entry artifact and requires the asset response to be
JavaScript rather than SPA fallback HTML.

## Preserved isolation and security

- Caddy continues to route only `/mission-control*`, `/engineering*`,
  `/mission-assets/*`, and `/api/v1/engineering/mobile*` to port `18008`.
- Ordinary ACP traffic continues to port `8080`.
- The Mission Control web artifact resolves API calls against the public
  same-origin `/` base; it contains no private container address or bypass.
- The isolated API must retain `ENVIRONMENT=preview`, trusted-forwarding
  enforcement, the `172.32.0.0/24` isolated network, protected secret mounts,
  and existing authentication/Company authorization.
- The unauthenticated Preview engineering API currently returns `401` with the
  fixed authentication-required contract.
- Built output contains no source maps, private-key patterns, live-token
  patterns, internal service URLs, or developer filesystem paths.

## Platform and release consistency

The current repository and both read-only Preview contract endpoints project
the same fingerprint:

`9bcde63480f88554305f4664de734c0137b320746427ce1447cf0fbf9e5c0ec0`

The release gate now compares four independent dimensions: backend SHA,
primary frontend SHA, Mission Control artifact SHA-256, and the single Alembic
head. Any mismatch returns `NOT_READY`; it never changes fingerprints to make
unrelated artifacts agree.

## Qualification

- Mission Control artifact: 86 files, `/mission-assets/`, verifier passed.
- Primary frontend production build: passed with `/` asset base.
- Frontend: 108 suites / 363 tests passed.
- Frontend ESLint and TypeScript: passed.
- Mission Control API, release consistency, platform contracts, and
  authorization: 50 tests passed on a fresh PostgreSQL database.
- Mobile contracts: TypeScript and ESLint passed; 14 suites / 118 tests passed.
- Ruff, MyPy, Python compilation, Node syntax, shell syntax, and
  `git diff --check`: passed.
- Fresh PostgreSQL migration reached current protected head `n0p8r16g3t9u`;
  this repair itself adds no migration or schema change.
- Container-engine build was unavailable locally because the Docker daemon was
  not running; the identical Docker build command invokes the qualified npm
  artifact build and verifier.

## Enterprise integration and deployment sequence

1. Integrate this branch into the then-current protected authority and rerun
   all packet qualifications if source changes intersect these files.
2. Record the protected commit, current single Alembic head, platform-contract
   fingerprint, current coherent rollback release, and its immutable image
   digests before replacing anything.
3. Back up Preview persistence using the accepted resilience runbook. This
   repair adds no migration, but Enterprise must still run the integrated
   release's normal migration gate.
4. Build the primary web image with `frontend/Dockerfile` and the Mission
   Control web image with `frontend/Dockerfile.mission-control` from the same
   protected checkout. Capture immutable image digests and the
   `MISSION_CONTROL_ARTIFACT_READY` digest.
5. Build the generic and isolated Mission Control API images from that same
   checkout. Configure both with fingerprint
   `9bcde63480f88554305f4664de734c0137b320746427ce1447cf0fbf9e5c0ec0`
   unless the integrated manifest command produces a different reviewed value.
6. Preserve the existing Mission Control isolated network, API service,
   trusted proxy CIDR, secret mounts, and web-to-API alias. Replace the old
   Mission Control web container with the dedicated image; do not attach its
   API to the public or ordinary frontend network for convenience.
7. Replace the remaining current-release containers as one controlled release.
   Run `scripts/platform-resilience release-check` with the expected and
   observed backend SHA, primary frontend SHA, Mission Control artifact digest,
   and schema head. Do not open the release unless it returns `HEALTHY`.
8. Validate/reload the existing Caddy route contract, then run
   `scripts/verify-mission-control-preview.sh`.
9. Verify `/mission-control`, `/engineering`, direct refresh, a real
   `/mission-assets/` JavaScript response, API `401` without a session,
   authenticated owner access, revoked/expired-session failure, identical
   platform contracts, primary routes, health/readiness, capacity/worker
   views, and phone-control projections.

## Rollback

Retain the complete last coherent backend, primary frontend, Mission Control,
and schema-compatible release before deployment. On failure, block the release
and either complete the candidate coherently or restore the complete known-good
application set. Do not roll back the database schema destructively, reuse a
newer Mission Control artifact with an older API, bypass authentication, or
remove the isolated network. Re-run the release gate and Preview verifier after
rollback.

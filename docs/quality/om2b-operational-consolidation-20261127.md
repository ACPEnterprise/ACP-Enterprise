# OM2-B operational application consolidation — 2026-11-27

## Authority and scope

- Consolidated baseline: `6aec17be3ac0bc1316975b0222f39bc7c9903837`
- Successor branch: `work/om2b-operational-consolidation-01`
- Consolidated implementation: `eaa5e77f38c44991e7d2b4a7759511050a53a3c6`
- Accepted source changes selectively transplanted: CSR/dispatch
  `a8f8ae13440e6bb144c7807356912e06a2907c29`, appointment cancellation
  `dae70c18db7290901860e46b64089cce9065c28c`, and timekeeping reconciliation
  `7aeaea5f84f0ae7f3eeee8a1f9db08c62e2913d8`.
- No merge of the obsolete OM2-B ancestry was performed.

The implementation retains the consolidated platform while adding accepted
operator-facing CSR/dispatch navigation, explicit appointment cancellation,
and timekeeping result reconciliation. It also carries the secret-free browser
harness and reviewer runbook. Hosted qualification gained opt-in port and
verified-existing-network isolation so it can coexist with inspection runtimes.

## Platform preservation

`scripts/verify-platform-corrections.py` passed all required invariants:
CI runtime, Node runtime, Redis secret custody, Scheduling timezone, release
clock isolation, and Customer test isolation. The final published SHA must be
used as `--candidate-sha` when independently repeating this check.

## Frontend qualification

Executed in the repository-pinned `node:24.22.3-alpine` container:

- Complete Vitest suite: **173 files passed; 802 tests passed**.
- Complete ESLint run: **PASS**.
- Production frontend build during hosted qualification: **PASS**.

## Hosted synthetic qualification

Executed `scripts/qualify-application-integration.sh` using disposable ports
`18183` and `15433`, an empty pre-verified Docker bridge, and task-specific
Buildx/Python cache directories. No credentials are recorded here.

- Idempotent bootstrap: PASS.
- Authenticated initial application workflow: PASS.
- Protected-principal authentication, authorization, and tenant isolation: PASS.
- Container-owned smoke-token custody: PASS.
- Service restart and fresh-session persistence readback: PASS.
- Bounded reader expiration and token authentication: PASS.
- Protected-principal provision/issue/replay/revoke/cleanup lifecycle: PASS.
- Runtime database identity, least privilege, and row security: PASS.
- Backup and isolated restore: PASS (429 public tables).
- Overall application integration acceptance: **PASS**.

The disposable qualification stack was removed by the harness. The existing
owner-inspection frontend at `http://localhost:18182` remained healthy and was
not replaced.

## Acceptance boundary

This is synthetic component and hosted integration qualification. The browser
harness is published for Laptop Master or an independent reviewer to run with
authorized disposable credentials; Chromium was not launched in this session.
This evidence is not actual All County operational acceptance. Owner Acceptance
Finding 001 remains open pending actual source/media recovery and authenticated
browser acceptance. No payroll, payment, provider, protected-source, or other
financial execution occurred.

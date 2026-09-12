# OM2-C authenticated Preview acceptance

Authority: `4514b5df6be66e50ee172085c622ae613e172086`

## Result

The bounded authenticated runner is prepared and qualified, but live authenticated
acceptance is gated. No sanctioned token or fixture attestation is installed in this
workspace, and the existing `acp-employee-beta-v1` tooling intentionally has no live
provisioning transport. OM2-C did not bypass that boundary or create owner authority.

## Mechanism

`backend/scripts/authenticated_preview_acceptance.py` composes the existing Preview
authentication and synthetic fixture contracts. It:

- accepts only `https://preview.allcountyhomeservices.com`;
- reads an opaque access token from a mode-0600 file and emits none of it;
- requires the token to be unexpired and to expire within one hour;
- requires a mode-0600, expiring Enterprise attestation for fixture
  `acp-employee-beta-v1`, marker `SYNTHETIC_BETA_ONLY`, exact Company/Branch IDs, and
  `real_data_access=false`;
- verifies the authenticated login ends in `.invalid`, exact Company/Branch context,
  minimum persona permissions, and absence of communication, money, Accounting,
  Payroll-execution, and payable-punch permissions;
- executes only fixed GET probes for CSR, Employee, office, or QBO evidence;
- parses responses but emits no Customer, Employee, financial, or source payload;
- performs no mutation and retains no refresh token or reusable credential.

The standard authentication session remains expiring and revocable and supplies the
server-side session/audit lineage. Enterprise must issue the token to a dedicated
synthetic identity through the accepted identity owner and deliver it outside Git.

Example after Enterprise installs the two restricted files:

```text
cd backend
<repository-python> scripts/authenticated_preview_acceptance.py \
  --persona csr \
  --token-file <restricted-token-path> \
  --attestation-file <restricted-attestation-path>
```

Run separate least-privilege identities/attestations for `csr`, `employee`, `office`,
and `qbo`; do not aggregate execution authority into one acceptance identity.

## Current deployed gate

Preview health is healthy but reports backend `b5dff4b0203fe9a725a0ff844279876f410cba12`.
Protected authority is `4514b5df6be66e50ee172085c622ae613e172086`.
Until Enterprise supplies a coherent deployment, dedicated synthetic identity,
fixture attestation, and short-lived access token, all requested authenticated routes
remain `DEPLOYMENT_OR_IDENTITY_GATED`, not operator accepted.

## Scheduling governance

`POST /api/v1/operations/jobs/{job_id}/schedule` remains absent from
`backend/app/platform/idempotency/mutation-coverage.v1.json`. The authoritative
mutation inventory test still fails with that sole missing operation. The handoff is
published on PR #218. The runner has no scheduling mutation mode; replay-governed
acceptance cannot proceed until Laptop1-A/Platform lands the classification and
Enterprise deploys it.

## Qualification

- Runner/fixture controls: 10 tests passed.
- Current protected Payroll readiness and Scheduling service delta on fresh
  PostgreSQL 16: 36 tests passed.
- Ruff: passed for runner and tests.
- MyPy: passed for the runner.
- Dry execution without credential material: fail-closed `BLOCKED`.
- Mutation registry: one known failure, the routed Scheduling operation above.

No Preview, Production, Customer, Employee, Timekeeping, Payroll, Accounting, payment,
communication, QBO, or HCP mutation occurred.

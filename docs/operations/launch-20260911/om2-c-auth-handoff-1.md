# OM2-C authenticated acceptance handoff

State: `EXECUTION_READY_BLOCKED_AUTH`. Enterprise is the only issuer. OM2-C does not
create identities, choose credentials, activate fixtures, or grant mutation authority.

## Exact persona envelope

All four identities use the same Enterprise-selected `acp-employee-beta-v1` synthetic
Preview Company and one explicit synthetic Branch. They must have
`has_all_branch_access=false`, a unique `.invalid` login, a token lifetime of at most
one hour, and an attestation lifetime of at most four hours. Each session is revoked
after its run; its Membership/onboarding fixture is revoked or reset through
`PreviewIdentityFixtureService.reset_identity`. Production access, Company
administration, communications management, Payment collect/apply/refund, Accounting
journal prepare/post/reverse, Payroll calculation/payment/remittance execution, and
payable own-time punch are prohibited for every persona.

| Persona | Exact minimum permissions | Fixture references | Mutation |
| --- | --- | --- | --- |
| CSR | `COMPANY_CUSTOMER_READ`, `COMPANY_JOB_READ`, `COMPANY_JOB_MANAGE`, `COMPANY_SCHEDULING_READ`, `COMPANY_SCHEDULING_MANAGE`, `COMPANY_DISPATCH_READ` | synthetic `customer_id`, `job_id`, `appointment_id` in the attested Company/Branch | None by default; existing-Job scheduling only when separately allowlisted in the attestation |
| EMPLOYEE | `COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ`, `COMPANY_JOB_READ`, `COMPANY_TIMEKEEPING_OWN_READ`, `COMPANY_PAYROLL_STATEMENT_OWN_READ` | synthetic assigned `job_id`; any time evidence must be non-payable | None; time mutation is not in this persona contract |
| OFFICE | `COMPANY_WORKFORCE_READ`, `COMPANY_MEMBERSHIP_READ`, `COMPANY_PAYROLL_COMPENSATION_READ`, `COMPANY_PAYROLL_TAX_AUTHORITY_READ`, `COMPANY_PAYROLL_DEDUCTION_AUTHORITY_READ`, `COMPANY_TIMEKEEPING_ADMIN_READ`, `COMPANY_PAYROLL_REPORTING_READ` | synthetic `employee_id` | None; no setup approval or Payroll execution |
| QBO_READ | `COMPANY_ACCOUNTING_REPORT_READ` | preserved or unavailable-state evidence only; no QBO credential | None; GET-only |

## Minimal Enterprise issuance sequence

Run from `backend` with the repository Python. Values shown in angle brackets are
non-secret UUIDs/digests or restricted file paths. Generate and review one plan per
persona; this command performs no mutation:

```text
python scripts/acceptance_identity_provisioning_contract.py plan \
  --persona <csr|employee|office|qbo> \
  --synthetic-login <unique-name>@acceptance.invalid \
  --company-id <synthetic-company-uuid> \
  --branch-id <synthetic-branch-uuid>
```

Enterprise then uses the existing in-process, audited service boundary—there is no
public fixture-minting route—to perform exactly:

1. `CompanyAdministrationService.create_role` and `assign_permission` with the plan's
   exact permission set.
2. `PreviewIdentityFixtureService.provision_identity` with
   `fixture_key=acp-employee-beta-v1`, `authorized=true`, the exact Branch, `.invalid`
   login, and reviewed role IDs. Activate only through the sanctioned onboarding path.
3. `AuthenticationService.authenticate` through Enterprise's restricted secret broker.
   Store only the returned access token in a mode-0600 transient file. Do not provide
   OM2-C a password or refresh token.
4. Record the session and authorization audit event IDs. Independently verify deployed
   `/backend-health`, frontend artifact digest, protected SHA, and the single deployed
   Alembic head.
5. Seal one attestation per persona. Omit `--allow-mutation` for the read-only run.
   Supply the exact persona-specific `--fixture-reference` arguments listed above:

```text
python scripts/acceptance_identity_provisioning_contract.py attest \
  --persona <persona> \
  --company-id <synthetic-company-uuid> \
  --branch-id <synthetic-branch-uuid> \
  --user-id <synthetic-user-uuid> \
  --session-id <session-uuid> \
  --audit-event-id <authorization-audit-event-uuid> \
  --authorized-by <enterprise-actor-reference> \
  --release-sha <deployed-backend-sha> \
  --protected-authority-sha <protected-sha> \
  --frontend-sha256 <deployed-index-sha256> \
  --schema-head <deployed-alembic-head> \
  --fixture-reference <key=synthetic-uuid> \
  --ttl-seconds 3600 \
  --output <mode-0600-attestation-path>
```

If Enterprise explicitly authorizes synthetic CSR scheduling, add only
`--allow-mutation /api/v1/operations/jobs/{job_id}/schedule`. The sealer rejects every
route outside the persona contract. The current runner remains GET-only, so a mutation
also requires a separately reviewed invocation; an attestation alone never performs it.

Enterprise hands OM2-C only the persona name, restricted token-file reference,
restricted attestation-file reference, and non-secret fixture/audit references. Secret
contents are never copied into commands, Git, logs, reports, or chat.

## Immediate read-only execution

Run each persona independently:

```text
python scripts/authenticated_preview_acceptance.py \
  --persona <persona> \
  --token-file <restricted-token-path> \
  --attestation-file <restricted-attestation-path> \
  --start-at <month-window-start> \
  --end-at <month-window-end>
```

The runner checks origin, health/backend SHA, frontend digest, attestation/token expiry,
synthetic login, exact Company/Branch, exact permissions, prohibited permissions, and
bound fixture references before emitting status-only evidence. Schema/protected SHA
are Enterprise-sealed preflight facts because Preview exposes no unauthenticated schema
endpoint. Rendered Month/Week/Day/Work Week and proposal behavior must then be inspected
with the same bounded session; an HTTP 200 alone is not operator acceptance.

After each persona run, Enterprise calls `AuthenticationService.revoke_user_sessions`,
verifies the token returns `401`, and calls `PreviewIdentityFixtureService.reset_identity`.
The report records revocation and fixture cleanup without credential material.

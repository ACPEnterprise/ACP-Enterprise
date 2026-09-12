# OM2-C acceptance identity provisioning contract

Protected authority: `27b89ecf1d702acbe75d0e1f95cf83c5f6bba5c9`

This contract prepares Enterprise to provision four dedicated, non-Production
acceptance identities. It does not provision them, issue a password, mint a token, or
contact Preview. Secret issuance remains behind Enterprise's existing identity and
secret-delivery boundary.

Authoritative files are
`backend/operations/preview-acceptance-identities.v1.json`,
`backend/operations/preview-acceptance-attestation.v1.schema.json`,
`backend/scripts/acceptance_identity_provisioning_contract.py`, and
`backend/scripts/authenticated_preview_acceptance.py`.

## Shared controls

Every identity is dedicated to `acp-employee-beta-v1`, uses a unique non-routable
`.invalid` login, has one explicit synthetic Company and Branch, has no all-Branch
access, and is separate from owner, real Employee, Migration, QBO OAuth, and Production
identities. The standard AuthenticationService creates the audited, revocable session.
The access token expires within one hour. The fixture attestation expires within four
hours and binds persona, User, session, Company, Branch, exact permissions, deployed
release SHA, authorizing Enterprise actor, and audit event identity.

The contract prohibits Company administration, Communications manage, Payment collect/
apply/refund, Accounting journal prepare/post/reverse, Payroll calculation/payment/
remittance execution, and own-time punch. These identities cannot send a real
communication, move money, post Accounting, execute Payroll, or create payable time.

## Personas

| Persona | Exact permissions | Purpose |
| --- | --- | --- |
| CSR | `COMPANY_CUSTOMER_READ`, `COMPANY_JOB_READ`, `COMPANY_JOB_MANAGE`, `COMPANY_SCHEDULING_READ`, `COMPANY_SCHEDULING_MANAGE`, `COMPANY_DISPATCH_READ` | Customer/search/detail, Job lookup, calendar/Dispatch, and eventual synthetic Job scheduling |
| EMPLOYEE | `COMPANY_TIMEKEEPING_OWN_READ`, `COMPANY_PAYROLL_STATEMENT_OWN_READ` | Own time state, Job-clock state, Timecard and own Payroll evidence, read-only |
| OFFICE | `COMPANY_TIMEKEEPING_ADMIN_READ`, `COMPANY_PAYROLL_REPORTING_READ` | Office Timecard review and Payroll summary/register evidence, read-only |
| QBO_READ | `COMPANY_ACCOUNTING_REPORT_READ` | Preserved QBO unavailable or admitted source-evidence projections, GET-only |

The versioned JSON contract lists every allowed GET endpoint. CSR's existing-Job
scheduling POST is conditional and must remain unused until its authoritative mutation
classification, protected integration, coherent Preview deployment, and synthetic Job
attestation all exist.

## Enterprise provisioning sequence

1. Confirm Preview reports the coherent protected release. Choose one synthetic Company
   and Branch containing only acceptance fixtures; never use an operational tenant.
2. Generate a non-mutating, non-secret plan for each persona:

   ```text
   cd backend
   <repository-python> scripts/acceptance_identity_provisioning_contract.py plan \
     --persona csr \
     --synthetic-login csr-<nonce>@acceptance.invalid \
     --company-id <synthetic-company-uuid> \
     --branch-id <synthetic-branch-uuid>
   ```

3. Through the existing authenticated Enterprise administration boundary, create one
   dedicated role per persona, assign exactly the plan's permissions, initiate the
   synthetic identity through `IdentityOnboardingService`, grant only the stated Branch,
   and verify `has_all_branch_access=false`. Retain onboarding, role, permission,
   Membership, and Branch-grant audit identities.
4. Through Enterprise's existing restricted secret-delivery mechanism, establish a
   transient acceptance credential and call standard `AuthenticationService.authenticate`.
   Write only the returned access token to a local mode-0600 file. Do not print or retain
   the password or refresh token. The access token must expire within one hour.
5. Record User, session, authorization audit event, release SHA and Enterprise authorizer
   in a mode-0600 attestation; the command refuses overwrite:

   ```text
   <repository-python> scripts/acceptance_identity_provisioning_contract.py attest \
     --persona csr \
     --company-id <synthetic-company-uuid> \
     --branch-id <synthetic-branch-uuid> \
     --user-id <synthetic-user-uuid> \
     --session-id <session-uuid> \
     --audit-event-id <audit-event-uuid> \
     --authorized-by <enterprise-actor-reference> \
     --release-sha <deployed-full-sha> \
     --ttl-seconds 3600 \
     --output <restricted-attestation-path>
   ```

6. Invoke the existing runner separately for each persona:

   ```text
   <repository-python> scripts/authenticated_preview_acceptance.py \
     --persona csr \
     --token-file <restricted-token-path> \
     --attestation-file <restricted-attestation-path>
   ```

The runner verifies Preview origin/release, `.invalid` login, session, exact Company/
Branch and persona permissions, prohibited permissions, expiry and attestation before
probing. It parses response JSON but emits no domain data.

## Revocation and cleanup

After each run, use AuthenticationService to revoke the exact session, verify the token
now returns `401`, revoke the synthetic Membership and pending onboarding request, and
deactivate the dedicated role if it has no other assignment. Dispose of local token and
attestation through the approved secret-material process. Preserve immutable onboarding,
authorization, session, revocation, and acceptance result audit records. Never delete
shared or non-fixture domain records.

## Current execution state

`PREPARED_NOT_ISSUED`. No sanctioned synthetic identity/token/attestation or accepted
live fixture adapter is present, so no authenticated Preview request was made. Scheduling
mutation coverage remains unresolved and was not duplicated in OM2-C.

Newly integrated PR #216 was independently qualified: 19 backend Job-clock/labor tests
passed on PostgreSQL 16; Mobile Job-clock/foundation passed 2 suites / 27 tests, plus
TypeScript and ESLint.

Protected PRs #229 and #231 were then integrated and their Timekeeping Payroll-input
eligibility/corrected-time acceptance intersection passed 20 tests on PostgreSQL 16.

Protected PR #235 Employee Payroll setup then passed 3 backend tests and 3 frontend
files / 10 tests; focused Ruff/MyPy, frontend ESLint, TypeScript and production build
passed. This qualifies the integrated implementation, not its deployment or operator
workflow.

The authoritative mutation inventory also finds all four new Payroll setup POST routes
unclassified. The exact identities were published to PR #235. Together with the
existing Job-scheduling POST, current authority has five missing mutation
classifications. These owner-lane governance defects do not authorize OM2-C repairs.

No Preview or Production mutation, real communication, payable time, money movement,
Accounting posting, Payroll execution, or QBO/HCP mutation occurred.

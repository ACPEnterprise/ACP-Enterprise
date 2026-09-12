# QBO real-company read evidence 1 — Enterprise integration packet

Date: 2026-09-12

## Result

`LIVE_QBO_AUTHORIZATION_BLOCKED`

`QBO_OWNER_ACTION_REQUIRED`: sign in to Preview as the authorized All County Company
administrator and complete one QBO Production OAuth connection session, selecting and
confirming the intended All County realm. ACP will fail before redirect if the Intuit
Production client is not mounted, and will fail after callback if the realm or exact
CompanyInfo identity does not match. No broader reconfiguration should be attempted
unless that deterministic response names a missing configuration item.

## Protected authority and recovered state

- Starting authority: `origin/customer-management-v1` at
  `b2cf7b60f1c927b4ba24fc6a49513b7d19c26a94`.
- Branch: `work/qbo-realcompany-read-evidence-1`.
- Local production acquisition: disabled before any provider call.
- Intuit Production Client ID: unavailable in this authorized runtime.
- Intuit Production Client Secret: unavailable in this authorized runtime.
- Production refresh token: unavailable in this authorized runtime.
- Verified production realm/Company marker: unavailable in this authorized runtime.
- Sandbox-only token: none found locally; sandbox success is not used as production
  evidence. Protected Preview token environment could not be inspected without an
  authenticated administrator context.
- Endpoint selection: production code is pinned to
  `https://quickbooks.api.intuit.com`; sandbox code is pinned separately to
  `https://sandbox-quickbooks.api.intuit.com`.
- Refresh lifecycle: generation-bound serialized token refresh and rotated refresh
  token persistence are implemented and qualified. Production and sandbox use
  physically distinct filenames and references.
- Preview Compose declares separate restricted production state and evidence volumes,
  mounts them at `/var/lib/acp-qbo-production` and
  `/var/lib/acp-qbo-production-evidence`, and defaults production enablement to false.
  Production credential/token files live under the restricted production state volume.
  Actual deployed file presence and permissions remain unverified because the approved
  SSH identity was denied.
- Preview read-only observation: healthy at deployed version `b5dff4b0`; production
  connection and QBO Accounting evidence endpoints both returned HTTP 401 without an
  approved identity. No protected response body was read.

The stored realm cannot currently be asserted to be All County. The correct state is
unavailable, not disconnected, sandbox-authorized, or live.

## `qbo-accounting-evidence/v1`

The existing OM2-B workspace contract now includes a stable bounded record index. Each
record exposes:

- source `QBO`;
- digest-bound realm/Company identity (raw realm and credentials remain protected);
- record type and native source record ID;
- provider `SyncToken` version where present;
- value state, amount where source-reported, and currency;
- cash/accrual basis;
- source as-of date and acquisition timestamp;
- snapshot completeness and refresh state;
- deterministic conflict state;
- `quickbooks_online_source_reported` authority;
- explicit `accepted_as_acp_accounting = false`.

The unavailable contract returns an empty record list, `realm_company_identity = null`,
unknown amounts, and no false zero. Existing accounts, Customers, Vendors, Invoices,
Bills, Payments, deposits, balances, reports, paging, and catalog-disposition evidence
remain owned by the bounded GET-only acquisition. No Customer master or ACP ledger is
created.

## Read-only acquisition boundary

If OAuth succeeds, the existing production runner supports the full bounded catalog,
including CompanyInfo, accounts, Customers, Vendors, Invoices, Payments, Bills,
BillPayments, purchases, deposits, transfers, journal entries and other declared QBO
families. Control reports retain registered report type, cash/accrual basis, report end
date, generation time and digest. Missing provider-dependent families remain explicit.

No acquisition was attempted because the production authority gate failed locally and
could not be evaluated in authenticated Preview. No QBO mutation endpoint exists in
the adapter; HTTP POST is rejected.

## ECO break-even continuation

`ECO.BREAK_EVEN.INPUT.READINESS.1` was continued independently. The existing
`eco.break-even-input-readiness.v1` contract remains policy-neutral and retains paid,
actual worked, productive Job time, actual labor cost, direct material, other direct
cost, overhead pool and earned-revenue comparison as distinct facts.

The bounded repair prevents Company break-even packets from silently:

- consuming another subject's evidence;
- combining different reconciliation periods;
- counting the same component/value digest twice;
- aggregating Branch evidence into a Company packet.

Missing inputs remain unknown, QBO source-reported amounts remain unaccepted, and no
break-even method, productive-hour definition, labor burden, overhead allocation,
model output or recommendation is selected.

## Environment boundaries

No QBO mutation, Accounting posting, Production deployment, money movement, Payroll
execution, Customer communication, frontend duplication, or policy value was created.
Preview was read-only and unauthenticated.

## Qualification

- QBO source, Business Economics and operational measurement: 444 passed.
- Focused QBO projection/production and break-even readiness: 35 passed.
- Changed-file Ruff and MyPy: passed.
- Python application/test compilation and `git diff --check`: passed.
- No migration or schema change.

# Workforce Employee timeline 1 — Enterprise handoff

## Authority

- Starting protected SHA: `4574d17a27104ea997dd92f2e53bda7cb31b90fb`.
- Independent of frozen PRs #341 and #343.
- No schema migration and no mutation endpoint.

## Timeline contract

`GET /api/v1/workforce/employees/{employee_id}/timeline` composes authorized,
Company-scoped history from existing canonical ACP records:

- Employee creation;
- protected onboarding and activation;
- Membership creation;
- role and ACP Employee Mobile role assignment/removal;
- capability evidence;
- bounded availability evidence;
- native Dispatch assignment history;
- Workday punches and Job clock events.

Every item includes the subject Employee, event time, authority label, source,
owner-readable description, authorized actor identity when recorded, and a safe
navigation reference where supported. The result is newest-first.

The endpoint does not expose compensation, W-4, bank, deduction, tax, Payroll
calculation, or payment information. It does not translate source evidence into
native ACP assignment history. A future source-certification integration may add
events only as `SOURCE_BACKED` after exact certified provenance exists.

## Owner experience

Team / Employees → Employee detail now includes History. Each event carries a
visible `ACP NATIVE` or `SOURCE BACKED` authority label. If history cannot be
loaded, the UI reports that no event was inferred.

## Qualification

- Timeline and platform tests: `12 passed`.
- Workforce route tests: `4 passed`.
- Ruff: passed.
- MyPy: passed.
- TypeScript production build: passed.
- Existing PostgreSQL-only field-readiness tests remain unavailable because the
  lane cannot resolve host `postgres`; this candidate adds no persistence.

No employee identity, availability, capability, assignment, Timekeeping, Payroll,
Preview, or Production state was changed.

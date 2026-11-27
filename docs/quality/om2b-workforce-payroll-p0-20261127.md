# OM2-B workforce and Payroll P0 handoff — 2026-11-27

## Scope and safety boundary

- Branch: `work/om2b-workforce-payroll-p0-01`
- Parent consolidation: `9020e26905c907dfab64d30aa8a8a29d232922e8`
- Operator implementation: `df818f8f0b4bcd89d52c9dadece666638d83ec6e`
- Browser qualification extension: `bbfa40eb7fbabc381553a822c06cf4dfc34e072f`

No payroll was submitted, no funds were transferred, and no external payroll,
tax, accounting, or provider system was mutated. All qualification used local
synthetic or disposable records.

## Operational corrections

- The supervisor Workforce page now presents one current-period review instead
  of two conflicting copies. Pay-period selection, Payroll navigation,
  submitted-entry approval, correction initiation, and detailed timecards are
  in one continuous operator flow.
- Persisted additional earnings are visible in the operating Payroll register,
  including explicit commission category and amount evidence when present.
  Missing earnings are not displayed as zero.
- A cross-contract test proves the expected nine-Employee operational roster
  (seven current plus two terminated/historically preserved) and ten retained
  historical workforce identities. The terminated identities remain unresolved
  and cannot gain operational access through reconciliation.
- The secret-free real-browser harness now includes authenticated Employees &
  Time, employee timecard, and Payroll Administration route checks and hashed
  screenshots in addition to the existing business workflow checks.

## Qualified workflow coverage

Existing application authority and the retained tests cover:

- current pay-period creation and selection;
- employee clock activity and submission of the latest recorded revision;
- supervisor correction, submitted-time approval, self-approval denial, and
  accepted-time persistence;
- weekly regular/overtime calculation, explicitly authorized additional
  earnings such as commissions, approved deductions, taxes, and liabilities;
- Payroll population assembly, calculation, review, review acceptance, approval,
  durable close preparation, reporting, and fail-closed missing-input behavior.

These are preparation and review workflows. Payment, filing, provider execution,
and financial transfer remain outside this handoff.

## Qualification evidence

- Complete frontend: **173 files / 802 tests PASS** using pinned Node 24.22.3.
- Frontend ESLint: **PASS**.
- Frontend production build: **PASS**.
- Focused workforce/timekeeping/Payroll backend selection: **43 PASS**. Four
  database-backed native-calculate tests could not resolve the standalone
  container hostname `postgres`; this was an isolated test-environment issue,
  not an assertion failure. The subsequent official hosted qualification used
  its managed PostgreSQL service and passed.
- Hosted disposable integration: authenticated initial flow, token custody,
  authorization, tenant isolation, restart/fresh-session persistence readback,
  bounded principal lifecycle, database least privilege/RLS, and backup plus
  isolated restore of 429 public tables: **PASS**.
- Platform preservation on the implementation SHA: all six required checks
  **PASS**.

## Browser handoff and acceptance boundary

Laptop Master or an independent reviewer can execute the published harness
using the existing secret-free procedure in
`docs/quality/om2b-real-browser-history-02-runbook.md`. The runtime must serve
the final branch SHA and credentials must remain in an approved local mode-0600
file. The harness now checks `/employees`, `/workday`, and `/payroll` and emits
mode-restricted screenshots and SHA-256 hashes.

Chromium was not launched from this managed session. Therefore real-browser UI
acceptance remains a Laptop Master/reviewer execution gate and is not claimed
by this receipt. Synthetic hosted qualification is not actual All County
operational acceptance, and Owner Acceptance Finding 001 remains open.

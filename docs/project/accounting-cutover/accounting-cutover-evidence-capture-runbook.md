# Accounting cutover evidence capture

This is an append-only evidence layer around the existing QBO control packets.
It captures the inherited state before correction, preserves source digests,
separates Beacon provenance from Luminary analysis and LIA decisions, and emits
a private package plus a sanitized derivative. It does not post journals, write
QBO, execute Payroll, or change accounting authority.

## Before corrections: immutable source baseline

Run this before any correction or native opening action. The source root must be
the mounted, digest-valid evidence directory; do not point it at a live QBO
connection or a directory containing credentials.

```bash
cd backend
umask 077
PYTHONPATH=. .venv/bin/python scripts/accounting_cutover_evidence.py baseline \
  --source-root "$QBO_PRODUCTION_EVIDENCE_ROOT" \
  --output-root "$CUTOVER_EVIDENCE_ROOT/source-baseline-before-corrections" \
  --authority-id "qbo-all-county-before-corrections" \
  --cutoff 2026-08-31
```

The command fails if the destination already exists. It copies source reports
and records their path, byte size, mode, and SHA-256. Secret-like files and
symlinks are excluded and recorded as exclusions; credentials are never copied
into the case-study package.

## Working registers

Prepare a protected JSON workbook containing `issues`, `provenance`,
`reconciliations`, `decisions`, `corrections`, `scorecard`, `milestones`, and
`unresolved_external_evidence`. The validator requires every issue to have a
provenance entry and every correction to reference an issue. Use these value
classes exactly:

- `SOURCE VALUE`
- `OBSERVED VALUE`
- `RECONSTRUCTED VALUE`
- `APPROVED VALUE`

Unknown, suspected, and unresolved values remain labeled; they are never
converted to zero for balancing convenience.

The register should cover HCP/QBO, banks, cards, inventory, fixed assets,
payroll, taxes, AR/AP, and equity/opening balances. Bundle related human
decisions in one LIA packet rather than issuing one technical question at a
time.

## Seal private and sanitized packages

```bash
cd backend
umask 077
PYTHONPATH=. .venv/bin/python scripts/accounting_cutover_evidence.py seal \
  --workbook "$CUTOVER_EVIDENCE_ROOT/accounting-cutover-workbook.json" \
  --output-root "$CUTOVER_EVIDENCE_ROOT/accounting-cutover-private" \
  --sanitized-root "$CUTOVER_EVIDENCE_ROOT/accounting-cutover-sanitized"
```

The private package contains the discrepancy register, Beacon provenance
ledger, Luminary reconciliation findings, LIA decision history, correction
journal, before/after scorecard, milestone reports, final reconciliation report,
first-native-close status, and simulation regression scenarios. The sanitized
package redacts customer, employee, vendor, bank, card, tax, credential, and
other sensitive values while preserving approved financial metrics.

Both destinations are create-once and protected (`0700` directories,
`0600` files). The package manifest records every emitted file digest. No
material is published externally; owner approval is required before any
sanitized report becomes commercial collateral.

## Existing control evidence to bind

The workbook should reference, without replacing, the existing sealed controls:

- 2026-08-31 Cash/Accrual control packets and successor registrations;
- the `$850.00` AR source-version conflict;
- empty AP reports as an accountant-confirmation candidate, not an assumed zero;
- `39271.71` ledger-supported Undeposited Funds requiring opening-control
  approval;
- per-card statement control still unavailable;
- legacy inventory valuation unavailable without physical count/cost basis;
- 92 COA classifications requiring owner/accountant judgment;
- payroll YTD/liability and tax-control evidence still required.

## Milestone and cutover discipline

The package emits SOURCE BASELINE, DISCOVERY, RECONSTRUCTION, DECISIONS,
CORRECTION, VALIDATION, CUTOVER, and FIRST NATIVE CLOSE reports. A first-native-
close report remains `PENDING` until the common cutoff, balanced opening
controls, Finance acceptance, and close receipt exist. Evidence capture may run
alongside cutover work; it is not a prerequisite to continue non-mutating
reconciliation.

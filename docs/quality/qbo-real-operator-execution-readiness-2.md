# QBO real operator execution readiness 2

## Dependency and boundary

This candidate is a successor to PR #512 and requires its canonical application
ledger and migration `q7s9u1w3y5a7`. It adds no QBO acquisition, writeback,
Accounting posting, account inference, payment, Payroll, or tax behavior.

## Normal operator path

An authorized user with `COMPANY_ACCOUNTING_RECONCILE` opens **Accounting →
QuickBooks migration**. The page preflights sealed evidence, displays source-family
counts, current dispositions, safe-majority percentage, the durable receipt, and the
human-readable review queue. **Apply safe majority** remains disabled until evidence
passes custody/digest validation and the operator acknowledges the boundary.

## Beta evidence custody

`docker-compose.preview.yml` already provides the required runtime contract:

- named volume `preview_qbo_production_evidence`;
- mounted at `/var/lib/acp-qbo-production-evidence` in the backend;
- `QBO_PRODUCTION_EVIDENCE_ROOT` points to that mount;
- `qbo-production-init` creates the protected directory with owner-only mode.

Release must verify that the existing named volume contains the completed sealed
acquisition. An empty volume is truthfully shown as unavailable. Do not copy source
evidence into a worker checkout or rerun acquisition merely to populate it.

## Release acceptance

1. Integrate and migrate PR #512, then this dependent candidate.
2. Confirm one Alembic head and `current=head`.
3. Confirm the configured QBO Company UUID matches the authenticated tenant.
4. Confirm the protected evidence volume is mounted and its latest bounded manifest
   and envelope digests validate.
5. Sign in with Accounting reconciliation authority and open
   `/accounting/quickbooks-migration`.
6. Confirm source families and counts are non-fabricated and `unexplained` is zero.
7. Review the explicit acknowledgment and select **Apply safe majority** once.
8. Retain the displayed receipt. Refresh and confirm the durable receipt and review
   queue remain visible. A retry after lost response must report exact replays rather
   than create duplicates.

No real application is executed by this worker candidate.

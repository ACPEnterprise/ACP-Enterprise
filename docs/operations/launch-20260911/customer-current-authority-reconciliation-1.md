# CUSTOMER.CURRENT.AUTHORITY.RECONCILIATION.1

## Integration boundary

- Base authority: `96d67cb73dbe4838e882e1551de5906eda598f4e`
- Candidate branch: `work/customer-current-authority-reconciliation-1`
- Integrate the complete candidate branch in commit order; it replaces the previously queued Customer wave on this base.
- Do not add `customer-office-operating-acceptance-2` to this wave.
- Schema impact: none. The candidate consumes existing Customer, Job, Scheduling, Invoice, payment, and migration-evidence contracts.

## Reconciled protected behavior

`JobsRoute.tsx` retains protected Customer and Service Location filtering, the Customer-context notice, and the **Show all Jobs** recovery action. It adds the candidate **Return to Customer** action without changing Scheduling behavior.

The protected Customer reliability test is reconciled to the authoritative Invoice workspace and Customer-balance hooks, and to current truthful empty/partial-state language.

## Qualification

- Customer/Invoice/AR affected frontend: 8 files, 50 tests passed.
- PostgreSQL Invoice/AR/source classification: 11 tests passed.
- Fresh PostgreSQL zero-to-head migration: passed; one head (`e5g7i9k1m3o5`).
- Production frontend build, static checks, and final protected-authority reconciliation are required before integration handoff is final.

## Post-deploy authenticated acceptance

Exercise name, phone, and address search; one and multiple Locations; no-current, current, and historical Jobs; Appointments; missing optional contacts; partial related work; backend failure and retry; and held/source-only versus admitted native records.

For financial evidence exercise native Invoice, authoritative AR, applied payment, unapplied receipt, and current, historical, stale, partial, conflicting, and unavailable states. Missing evidence must never render as zero. Real SOURCE.4 population completeness remains gated on Migration admission evidence and must not be inferred from a rendered page.

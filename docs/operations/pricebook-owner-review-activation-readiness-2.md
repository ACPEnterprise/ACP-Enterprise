# Price Book owner review and activation readiness 2

## Integration order

This candidate is a strict successor to PR #368. Enterprise Operations must
integrate and execute #368 admission first, then reconcile/merge this candidate.
Expected migration order:

`n0p8q16g3t9u -> o1q9r27h4u0v -> p2r0s28i5v1w`

No command in this packet activates a real price.

## Owner workflow

1. Open Price Book and search for the service code.
2. Inspect the candidate value, workbook sheet/row, derivation, tax review,
   material mapping, and source-conflict state.
3. Create the ACP draft price version with the intended selling price, certified
   tax classification, and effective date.
4. Open **Review activation** for that exact draft.
5. Owner approves selling price and effective date. A user with Accounting
   Finance Approve authority separately approves tax classification.
6. A Price Book activator explicitly authorizes that exact revision for a later
   activation command.
7. Activation remains a separate button and transaction. Any draft edit makes
   all earlier approvals stale. Audit history records each approval,
   authorization, activation, and supersession.

## Bounded first packet

| Code | Candidate evidence | Material state | Remaining requirements |
| --- | --- | --- | --- |
| SVC-001 | $129 owner workbook override; Service Calls row 5 | No source component cost | ACP price approval; accountant tax approval; effective-date approval; explicit activation authorization |
| SVC-002 | $239 owner workbook override; Service Calls row 6 | No source component cost | ACP price and after-hours-policy approval; accountant tax approval; effective-date approval; explicit activation authorization |
| DRN-001 | $195 workbook formula; Drain Cabling row 5 | $5 aggregate evidence; mapping required | ACP price approval; accountant tax approval; effective-date approval; explicit activation authorization; material mapping remains visible but does not become Inventory consumption |
| DRN-002 | $300 workbook formula; Drain Cabling row 6 | $8 aggregate evidence; mapping required | ACP price approval; accountant tax approval; effective-date approval; explicit activation authorization; material mapping remains visible but does not become Inventory consumption |

The 39 Water Heater conflicts remain held. This release adds no inference or
resolution for them.

## Qualification and acceptance

- Fresh PostgreSQL zero-to-head, one head, `current=head`, and Alembic drift.
- Price Book, Estimate snapshot, and Job Materials regressions.
- Verify candidate activation rejects missing/stale approvals.
- Verify approval order, explicit activation authorization, activation audit,
  supersession, and historical Estimate snapshot preservation.
- Frontend test, ESLint, TypeScript, and production build.

After Preview deployment, stop before activation and have Michael review these
four drafts. Enterprise must obtain a separate explicit activation instruction
identifying exact service codes and draft revisions.

# Invoice and Manual Payment Controlled Acceptance

## Authority boundary

ACP native Invoice authority is derived only from a completed Job and the exact accepted Estimate revision. Invoice lines retain sold commercial snapshot identity and digest. Issuing creates the native receivable obligation; subsequent credits, write-offs, payment applications, reversals, and voids append evidence rather than rewriting the sold Invoice.

QBO remains retained financial authority for controlled launch. Recording a manual payment in ACP does not create an Accounting journal, QBO transaction, bank deposit, processor event, or settlement assertion.

## Bounded operator successor

An authorized operator may open an issued Invoice and record either:

- `check`; or
- `other_manual` evidence.

The command requires amount, reference, current Invoice version, Branch, occurrence time, and an idempotency key. It atomically:

1. creates immutable manual receipt evidence;
2. creates one fully consumed native receipt-evidence record;
3. appends one AR payment application;
4. reduces the Invoice open balance;
5. moves the Invoice to `partially_paid` or `paid`;
6. emits a safe Business Event.

The resulting record is permanently marked `settlement_state=not_asserted` and `accounting_state=not_posted`. Only the last four reference characters are returned to the UI; exact reference evidence is represented by a digest for duplicate prevention.

Exact command replay returns the original receipt and current Invoice. Conflicting idempotency-key reuse, duplicate reference evidence, stale Invoice versions, overpayment, foreign Company/Branch scope, draft/voided/paid Invoices, and unauthorized users fail closed.

## Permissions

Recording requires both `COMPANY_PAYMENT_COLLECT` and `COMPANY_INVOICE_APPLY_PAYMENT`. Viewing history requires both Payment and Invoice read authority. This candidate does not broaden the Office Manager role; Lianne remains unable to record payments unless the owner separately changes the established role policy.

## Owner acceptance

Use a sanctioned real completed/sold Job and real check/manual evidence only after Enterprise deploys the candidate:

1. Open Invoices through normal navigation.
2. Create a draft from the completed Job and accepted Estimate without entering UUIDs outside existing product navigation where links are available.
3. Verify Customer, service location, Job, sold Estimate snapshot, totals, terms, due date, and QBO retained-authority notice.
4. Issue the Invoice and confirm the entire amount becomes open.
5. Present/send it only through an independently accepted Communications workflow; Invoice authority itself must continue to show delivery as unasserted until delivery evidence exists.
6. As an authorized owner, record a partial check using the real amount and reference.
7. Confirm one manual-payment history entry, `settlement not asserted`, `Accounting not posted`, `partially_paid`, and the exact remaining balance.
8. Refresh and verify no duplicate receipt/application appears.
9. Attempt the same reference with a new command and verify it fails closed.
10. Record the remaining authorized payment only if it actually occurred; verify `paid` and zero open balance.
11. Verify Customer balance/history and Job/Invoice navigation.
12. Reconcile retained QBO authority separately; do not treat ACP evidence as a QBO posting.

## Enterprise Operations handoff

1. Integrate the candidate onto current protected authority.
2. Apply Alembic revision `q3s1t29j6w2x`.
3. Run Invoice, Payment, Customer, Job, authorization, idempotency, frontend, and migration qualification.
4. Deploy through Enterprise release controls; OM2-B does not deploy.
5. Verify the manual-payment POST route requires both permissions and its history GET route is tenant/Branch scoped.
6. Run the owner acceptance sequence with one sanctioned real Invoice/check.
7. Record the candidate/deployed SHA and acceptance evidence.
8. Roll back the application artifact first if needed. Do not downgrade after real evidence exists; preserve the table and disable the route instead.

Remaining gates are real owner acceptance, separately accepted Invoice delivery evidence, and retained QBO reconciliation. No payment-processor integration is required for this bounded launch path.

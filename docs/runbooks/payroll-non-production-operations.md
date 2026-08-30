# Payroll non-production operations

This runbook exercises ACP Payroll with synthetic identities and evidence only. It does not select legal rules, providers, bank destinations, Company accounts, or real Employee inputs.

## Configure and open

1. Approve Company Payroll policy, schedule, compensation, tax/deduction, payment-destination, remittance, and Accounting mapping authorities with distinct authorized actors.
2. Admit complete historical/opening evidence before treating quarter-to-date or year-to-date totals as authoritative. Partial coverage must remain `partial` or `unavailable`.
3. Open the intended pay period and verify the full expected Employee population. Resolve each Employee to ready, blocked, excluded, or not applicable; never omit one silently.

## Calculate, review, and approve

1. Verify approved, sealed time evidence where required.
2. Calculate and persist gross-pay candidates, then tax/deduction/net-pay candidates.
3. Review Employee results and assemble the Company/pay-period run.
4. Inspect blockers and reconciliation. Review and finally approve the run using explicit, separate permissions.

Approval is Payroll evidence only. It is not payment, remittance, filing, or Accounting posting.

## Downstream operations

1. Prepare payment instructions and a release package from the approved run. Confirm destination readiness without displaying protected bank data.
2. Use synthetic providers only in test. Submission or acknowledgement is not settlement; only explicit settlement evidence may settle an instruction.
3. Assemble remittance obligations from approved liabilities. Verify destination and due-date authority, review, approve, and reconcile partial or uncertain outcomes without blind retry.
4. Issue protected pay-statement artifacts only from approved Payroll evidence. Delivery notifications contain an authenticated link, never statement amounts or attachments.
5. Prepare period, quarter, and annual reporting snapshots. Approve an explicit provider-neutral compliance schema before preparing a filing-package preview. Every package remains `prepared_not_submitted`.

## Corrections and close

1. Preserve original Payroll, payment, reporting, statement, and Accounting evidence.
2. Initiate an append-only adjustment, calculate only its signed delta, review it, and apply it once to a purpose-specific successor authority.
3. Create successor statements and amended filing-package evidence where the correction changes accepted reporting. Never overwrite the predecessor.
4. Reconcile Payroll totals to run membership, payment instructions and settlement, remittance obligations and settlement, reporting totals, Accounting-ready facts, and admitted Economics evidence.

## Blocked-state troubleshooting

- Missing or conflicting time, compensation, policy, tax, deduction, destination, or history evidence: repair the relevant authority; do not calculate around it.
- Closed Accounting period: preserve the requested economic date and follow native Accounting adjustment/reconciliation authority; do not silently move the entry.
- Uncertain payment or remittance: stop automatic retry and reconcile provider evidence.
- Artifact verification failure: deny retrieval, retain evidence, and regenerate only from verified immutable source authority.
- Incomplete history: display YTD/QTD as unavailable or partial.

## Real-use gates

Owner approval remains required for real Employee data, compensation and elections, jurisdictional/legal rules, providers and credentials, bank destinations, filing schedules, Chart of Accounts mappings, recognition/accounting-date policies, actual payment/remittance/filing, real Accounting posting, Preview release, and Production operation.

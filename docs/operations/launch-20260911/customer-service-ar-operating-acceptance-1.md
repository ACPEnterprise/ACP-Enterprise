# Customer Service / AR Operating Acceptance 1

## Authority and integration

- Protected authority inspected: `d52d117801d72d04e81afac157671c97a941efa0`.
- This branch is intentionally stacked on `work/customer-office-workflow-1` at `da23d1f3822289f552d2efd133adbddce8224948` so the qualified Customer workflow is reused rather than recreated.
- Integrate the predecessor first, then integrate only this branch's commits beyond `da23d1f3`, or reconcile mechanically after the predecessor lands.

## Financial semantics

The Customer workspace consumes existing customer-scoped Invoice workspace and Customer balance contracts. It labels native evidence `CURRENT_AUTHORITATIVE`, distinguishes open from historical native Invoices, presents applied payments separately from unapplied receipts, and carries the balance contract's exact as-of date and currency.

`legacy_evidence_incomplete` produces `PARTIAL historical evidence`. The Customer balance response does not currently carry a customer-scoped stale/conflicting source classification, so the UI does not manufacture either state. QBO/HCP evidence remains historical source authority and is not presented as live ACP Accounting truth.

## Bounded owning-lane contract packet

Owner: Migration / Accounting source-evidence lane.

Observed contract: `GET /api/v1/invoices/customers/{customer_id}/balance?as_of=...` returns native totals, currency, as-of, and `legacy_evidence_incomplete`.

Missing bounded projection: a customer-scoped source-evidence reference/status capable of distinguishing `HISTORICAL_SOURCE_EVIDENCE`, `PARTIAL`, `STALE`, `CONFLICTING`, and `UNAVAILABLE`, with source snapshot/digest and source as-of date where admitted. The office UI must not query or filter the global QBO evidence packet by inference.

Requested owning-lane decision: either extend an accepted read-only customer financial evidence projection or explicitly declare that customer-scoped source status remains unavailable. Do not change Customer identity/admission semantics and do not make source balances native ACP balances.

## Authenticated Preview acceptance after Migration admission

Use accepted authentication and real admitted non-Production records. Record deployed SHA, Company/Branch, Customer/Location/Job/Appointment/Invoice IDs, accepted Migration packet identity/digest, native balance as-of, source as-of, and every observed assertion. Do not mutate source data or perform financial commands.

1. Open-invoice Customer: verify open Invoice appears only under Open invoices; open amount/currency/status match Invoice authority; follow Invoice and return to the same Customer.
2. Paid-invoice Customer: verify paid Invoice appears under Historical invoices and is not counted as open merely because it exists.
3. Unapplied-receipt Customer: verify the receipt amount is separate from applied payments and does not reduce a specific Invoice unless application evidence exists.
4. No-financial-evidence Customer: verify a truthful native empty/unavailable state; no zero is displayed unless the authoritative balance response explicitly reports zero.
5. Incomplete-history Customer: verify `PARTIAL historical evidence`, source limitation, and absence of any “complete” claim.
6. Multiple-Location/Job Customer: navigate Location → current Job → Appointment → Invoice/AR → Customer; verify identity and filters survive each return.
7. Current-plus-history Customer: reconcile current/completed/cancelled Job counts against the customer-filtered paginated Job workspace.
8. Appointments: verify upcoming Appointment identity and bounded window; absence outside the window must not be called no history.
9. Service history pagination: traverse Customer timeline and customer-filtered Job pages; retry a deterministic failed history request without losing Customer context.
10. Source classification: where the owning lane provides it, verify `HISTORICAL_SOURCE_EVIDENCE`, `PARTIAL`, `STALE`, `CONFLICTING`, and `UNAVAILABLE` independently. Until then, confirm the UI does not invent stale/conflicting status.
11. QBO gate: verify no UI claims live QBO when OAuth/provider admission is incomplete and no source number is labeled ACP Accounting authority.
12. Phone width: inspect open/historical Invoice lists, AR evidence, source limitations, Jobs, Appointments, and return links without horizontal blocking.

No Customer communication, payment execution, Accounting posting, money movement, Preview mutation outside approved synthetic fixtures, or Production operation is authorized.

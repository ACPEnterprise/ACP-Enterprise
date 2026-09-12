# Customer source evidence classification

`CUSTOMER.SOURCE.EVIDENCE.CLASSIFICATION.1` extends the existing Customer balance response with server-resolved, Customer-scoped evidence classifications. It does not create source identity or reconcile QBO/HCP records.

## Authority boundary

- Native Invoice, AR ledger, and Payment receipt evidence is `CURRENT_AUTHORITATIVE`, `PARTIAL`, or `CONFLICTING` according to its accepted native state.
- A historical source classification is returned only for an accepted `CustomerSourceIdentity` in the authenticated Company, authorized Branch, and requested Customer scope.
- The linked migration run supplies acquisition time, source digest, and completeness. Missing source as-of evidence remains absent.
- When no accepted Customer source identity exists, the response is `UNAVAILABLE`. The service never searches a global QBO/HCP projection by label and never turns absence into a zero balance.
- Staleness remains an explicit supported contract state, but is not inferred from elapsed time without authoritative source freshness evidence.

The API evidence includes Company/Customer scope and opaque source identity/digest for reconciliation clients. The ordinary office UI intentionally displays only source, classification, dates, and completeness.

## Post-SOURCE.4 authenticated acceptance

For an authorized office user in Preview, verify each case from Customer detail:

1. A Customer with native open and paid Invoices shows current ACP balance evidence, correct currency, applied payments, and unapplied receipts separately.
2. A Customer with an admitted HCP identity shows historical source evidence with the accepted acquisition date and completeness.
3. An unresolved/incomplete admitted run shows partial evidence and does not claim complete history.
4. A Customer without accepted source identity shows source evidence unavailable; no source balance or zero is inferred.
5. A native Invoice requiring reconciliation or a disputed receipt shows conflicting evidence.
6. A stale classification supplied by authoritative freshness evidence is visibly stale.
7. Another Company, unauthorized Branch, or another Customer cannot retrieve or infer the classification.
8. Source identity and digest are not displayed in the normal Customer UI.

QBO OAuth/live-source availability and Migration identity admission remain owning-lane gates. No source, Accounting, Payment, or Customer mutation is part of this capability.

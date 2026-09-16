# Customer History real-world acceptance continuous 1

## Authority and frozen product candidate

- Starting protected authority inspected: `b5c8f427d48028144d58cf7a76e6f4a33729feb5`.
- Ending protected authority inspected: `e42a0862bf7c893a8b916db0eecba16c731e3df6`.
- Frozen product candidate: `origin/work/customer-history-product-operations-complete-2` at `076b74736a71d6b13301223dfc4a5b9bec81c39c`.
- Protected authority does not yet contain either frozen candidate commit.
- This mission does not cherry-pick, amend, rewrite, or repackage the frozen candidate.

## Evidence custody

The required sealed archive was not present at the approved destination during this run. Its state remains `BLOCKED_EVIDENCE_TRANSFER`, not evidence absence. No SSH transfer was attempted, no packet was regenerated, and no SOURCE.4 disposition was inferred.

The prior blocked audit packet remains at:

`/Users/michaelfouse/.acp-enterprise/audits/source4-customer-successor-evidence/customer-successor-evidence-audit-20260914.json`

The exact 20-record audit must resume only after the archive and its three members pass the owner-supplied SHA-256 and permission checks.

## Real-corpus prerequisite result

No qualified real All County Customer corpus is locally available to Laptop1-B.

The local ACP database was inspected read-only and contains 341 Customer rows distributed across 265 Companies, with no Company containing more than three Customers. It is therefore an accumulated development/test-fixture database and must not be represented as real All County acceptance evidence.

That database also predates the admitted Estimate, Invoice, Payment, and refund tables. Its available aggregate shape was:

- 341 Customers, including 5 archived;
- 284 Service Locations;
- 46 Jobs across 42 Customers;
- 188 Appointments across 144 Customers;
- 8 Customers with multiple Locations;
- no qualified complete Customer-to-Payment chain.

These counts are prerequisite evidence only. They are not a real acceptance corpus and are not a statement about the Migration population.

## Current acceptance classification

| Area | Result | Reason |
| --- | --- | --- |
| Frozen candidate search contract | `QUALIFIED_FIXTURE_BACKED` | Name, number, contact, phone, email, address, state filtering, stable pagination, and tenant isolation have deterministic tests. |
| Real 25-Customer corpus | `SOURCE_HISTORY_NOT_ADMITTED` | No qualified real All County Company population is available locally. |
| Protected Customer product | `INTEGRATION_REQUIRED` | Protected authority does not contain the frozen candidate. |
| Real Estimates | `SOURCE_HISTORY_NOT_ADMITTED` | No accepted real Customer-scoped admitted corpus is available here. |
| Real Invoices / AR | `SOURCE_HISTORY_NOT_ADMITTED` | No accepted real Customer-scoped admitted corpus is available here. |
| Real Payments / refunds | `SOURCE_HISTORY_NOT_ADMITTED` | No accepted real Customer-scoped admitted corpus is available here. |
| SOURCE.4 UPDATE audit | `BLOCKED_EVIDENCE_TRANSFER` | Required sealed archive is absent locally. |
| Preview owner acceptance | `INTEGRATION_REQUIRED` | Enterprise integration and authenticated Preview access are required. |

Missing relationships must remain one of `SOURCE_HISTORY_NOT_ADMITTED`, `SOURCE_MISSING`, `BINDING_MISSING`, `AUTHORIZATION`, or `EXPECTED_PARTIAL_STATE`. They must not be converted to zero or a product defect without evidence.

## Bounded product defects to reconcile after integration

These issues are in the frozen candidate and cannot be repaired on a branch based only on current protected authority without recreating or mixing the frozen work:

1. The primary completeness badges render uppercase contract labels. The owner-facing label and explanation should instead be:
   - Complete — “ACP has the complete admitted history for this Customer.”
   - Partial — “ACP has some of this Customer's history, but additional source history has not yet been admitted.”
   - Source-backed — “This history is available from a legacy source and has not become ACP-native authority.”
   - Unavailable — “ACP does not currently have authoritative evidence for this history.”
2. Job timeline navigation carries an explicit Customer return target, but Appointment, Estimate, and Invoice timeline links do not all carry the same explicit return contract. After integration, acceptance must prove browser and product navigation return to the same Customer without losing roster/search context.

Enterprise should integrate the frozen candidate first, then request a narrowly based successor correction if these defects remain after reconciliation.

## Owner acceptance script

Run this only after the frozen candidate is protected-integrated and Migration publishes an admitted real corpus. Use operator-visible Customer names/numbers supplied by the admitted roster; never use internal UUIDs.

Select 5–10 Customers covering: multiple Locations; current Job; completed Job; canceled Job; Estimate; open Invoice; paid Invoice; applied Payment; unapplied receipt; archived Customer; partial/source-backed evidence.

For each selected Customer:

1. Search by exact name and open the Customer.
2. Repeat with a partial name and Customer number.
3. Where present, repeat by contact name, phone, email, and Service Location address.
4. Confirm the Current, Archived, and All filters return the expected record state without duplicates.
5. Confirm identity, archive state, contacts, Location count, open/historical Job counts, Appointment count, Estimate count, Invoice count, Payment count, and latest admitted Job.
6. Open each Service Location and confirm Jobs and Appointments remain bound to that exact Location.
7. Inspect the newest-first timeline. Every item must show type, date, concise description, source/authority, and a valid destination.
8. Open one Job and verify Customer, Location, lifecycle, Appointment, assignment, and any authoritative commercial/time evidence.
9. Open available Estimate, Invoice, and Payment evidence. Never infer a Job link or treat an unapplied receipt as an Invoice payment.
10. Return to the same Customer and confirm the roster/search context remains usable.
11. Read the completeness explanation. Missing source history must not appear as zero or complete.
12. For an archived Customer, confirm search, read-only detail, timeline, authorized Restore, and absence of duplicate creation.

Record deployed SHA, authenticated role, Company/Branch, operator-visible search term, observed source/as-of state, relationship availability, return-navigation result, and any missing stage. Do not record credentials, tokens, or protected payloads.

## Required Migration handoff

OM1 Migration must provide:

- the sealed SOURCE.4 custody archive at the approved path;
- the qualified real Company-scoped Customer population available for acceptance;
- exact admitted Customer/Location/Job/Appointment/Estimate/Invoice/Payment bindings;
- explicit source-only, held, conflicting, stale, partial, and unavailable states;
- 5–10 operator-safe Customer names/numbers covering the acceptance cohorts, or a protected query mechanism that selects them deterministically.

No Migration code, identity classification, source binding, Preview record, or Production record was changed by this mission.

# Revenue Cycle operational authority reconciliation

## Current authority

This packet was prepared from protected `origin/customer-management-v1` at
`a65a104c21282fd8f94a2e9bac37ba576a91a75c`. It is a worker reconciliation
packet; it does not merge, deploy, or admit source records.

The repository's sealed HCP.SOURCE.4 evidence records 1,307 Estimates, 5,756
Invoices, 4,308 payment assertions, and 28 refund assertions (12 with native
refund IDs). Those are sealed acquisition counts, not a claim about current
tenant rows. The sealed raw package is not present in this worker worktree, so
no source record was imported or counted as current here.

## Authority map

| Area | Protected implementation | Classification | Boundary |
|---|---|---|---|
| Estimate identity, Customer/Job scope, revisions, acceptance | `app/estimates` | COMPLETE for ACP-native work | Accepted revision and Company/Branch scope are required. |
| Estimate-to-Job relationship | `EstimateJobConversion` | COMPLETE | Conversion binds exact estimate revision, Job, Customer, location, and Branch. |
| Invoice creation and sold lineage | `app/invoicing` | COMPLETE | Requires completed Job, accepted current revision, and immutable sold-line evidence. |
| Invoice lifecycle and AR balance | `app/invoicing` | COMPLETE | Draft/issued/partial/paid/adjusted/voided/cancelled; AR append-only evidence. |
| Payment processor intent/receipt/application/refund | `app/payments` | COMPLETE for provider-neutral runtime | Provider outcome is separate from Invoice AR and settlement/accounting truth. |
| Manual/check payment collection | Protected authority has no route | MISSING in protected SHA | PR #370 supplies a bounded worker-only successor; Enterprise integration required. |
| HCP Estimate/Invoice/Payment admission | `operational_migration.financial` and source identities | PARTIAL / SOURCE_REQUIRED | Exact source graph and sanctioned migration context are required; no heuristic links. |
| HCP refund assertions | `hcp_financial_history` classification | SOURCE-BACKED, non-aggregating | Refunds without native IDs remain unlinked evidence; no fabricated native refund. |
| HCP/QBO overlap | reconciliation readiness contracts | BLOCKED BY AUTHORITATIVE DATA | Held from aggregation until exact QBO reconciliation. |
| Invoice delivery/send | Communications boundary | PARTIAL | Invoice authority does not assert send or delivery. |
| Accounting posting/settlement | QBO/Accounting authority | OUT OF OM2 SCOPE | No ACP posting or settlement is created by this lane. |

## Admission invariants

Financial migration preserves source system, provider IDs, source status,
source digest, run identity, parent identity, and Company/Branch scope. Exact
source identity replay is classified duplicate; contradictory or unresolved
parents are held. A payment assertion never authorizes money movement. HCP and
QBO evidence is not aggregated, and evidence-only invoices cannot receive a
fabricated native Invoice or payment application.

## Adversarial coverage available

The protected suites cover duplicate/replay and idempotency, parent-resolution
failures, partial payment and application, refund/reversal state, stale and
contradictory updates, Company/Branch scope, authorization, and source-history
classification. Current protected API routes expose native Invoice workspace,
Invoice detail, AR balance, provider payment intents/receipts/applications, and
provider refund requests. No protected manual-payment route exists yet.

## Exact operational gates

1. Enterprise must integrate PR #370 (`fcce4a2f`, currently worker-only) if
   controlled manual/check collection is required.
2. Migration must provide the sealed HCP package and sanctioned Company/Branch
   context before any historical admission run.
3. Exact HCP-to-ACP parent identities must be proven before accepting Estimate,
   Invoice, or Payment rows. Unresolved source refunds remain evidence-only.
4. QBO overlap and current balance/application reconciliation require
   accountant/owner authority; no net AR is inferred.
5. Invoice presentation/delivery requires a separately accepted Communications
   workflow.

## Enterprise handoff

Use this packet with the protected migration and Revenue Cycle suites. Do not
merge from this lane. Do not deploy. Treat `a65a104c` as the protected base and
PR #370 as a separate candidate requiring its own integration qualification.


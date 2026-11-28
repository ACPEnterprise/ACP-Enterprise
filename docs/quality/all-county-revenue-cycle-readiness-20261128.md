# All County revenue-cycle readiness handoff — 2026-11-28

## Decision

`COMPLETE_REVENUE_CYCLE_OPERATIONAL_READINESS=FAIL`

The native, non-money-moving customer-to-cash path is qualified in an isolated
environment. Complete operational readiness is not asserted because the current
application has no admitted live payment processor, legally qualified customer
signature/delivery channel, or complete direct/progress/change-order billing
authority. This packet does not convert those external or product gates into a
passing result.

## Authority and safety boundary

- Parent application authority: `28be5861ee0c9a51b0c8c32866f8d75519de5a68`.
- Isolated branch: `work/om1a-revenue-cycle-readiness-16`.
- All acceptance transactions used generated identities in disposable
  PostgreSQL 16 and Redis 7 containers.
- No QuickBooks, HCP, processor, bank, card, ACH, customer-communication,
  hosted environment, protected database, or historical financial record was
  read or mutated.
- The candidate adds migration `y4z6b8d0f2h5`, directly after
  `x3y5z7a9c1e4`. It expands only the enumerated non-settlement manual-payment
  evidence methods. The downgrade refuses to proceed when expanded-method
  evidence exists; it never deletes or rewrites a financial record.

## Qualified native path

The assembled acceptance gate now performs the following through the real,
authenticated HTTP surface:

1. Create a governed Price Book category, tax classification, service version,
   labor/material cost inputs, active price, and immutable commercial snapshot.
2. Create and revise an Estimate, calculate a 10% discount and 7% synthetic tax,
   then retain immutable revision 2.
3. Record send, view, and synthetic customer-approval evidence. No customer
   communication or legal-signature validity is claimed.
4. Convert the approved Estimate once to a Job, then activate, start, and
   complete that Job.
5. Create and issue one Invoice from the accepted Estimate/Job lineage without
   re-entering price or tax facts.
6. Record and apply a partial cash receipt and a final check receipt. The
   Invoice reaches paid with two retained receipt records and a zero Customer
   open balance.
7. Verify that neither receipt claims settlement or Accounting posting, and
   that a second tenant cannot read the Invoice.
8. Restart backend and frontend services and read the Estimate, Job, Invoice,
   and payment history in a fresh authenticated session.
9. Render the Estimate at desktop size, the Invoice/payment history at tablet
   size, and the Revenue Cycle at mobile size in a real headless browser.

The manual evidence contract now distinguishes `cash`, `check`,
`ach_external`, `card_external`, and `other_manual`. The external ACH/card
choices require independently verified processor evidence. They do not charge,
debit, settle, post to QuickBooks, or create Accounting authority.

## Capability disposition

| Requirement | Current disposition |
| --- | --- |
| Existing/new Customer, Location, Price Book, discounts, tax, revisions, options, Estimate-to-Job conversion | Qualified native foundation; real All County policy/catalog acceptance remains human-governed. |
| Approved Estimate to completed Job to issued Invoice | Qualified with immutable source lineage and no duplicate entry. |
| Multiple and partial manual payments; cash/check/external ACH/card evidence | Qualified as non-settlement evidence with idempotency and complete audit history. |
| Historical HCP/QBO distinction | Preserved; synthetic native records do not alter or masquerade as historical source evidence. |
| Direct Invoice authoring independent of accepted Estimate/Job | Not implemented as complete authoritative workflow. |
| Custom Estimate lines outside a governed Price Book snapshot | Not implemented. |
| Change orders, deposits, progress schedules, and final-billing schedules | Not implemented as complete authoritative workflows. |
| Customer-ready Estimate/Invoice/receipt artifacts and delivery | Partial UI only; no qualified artifact/delivery authority. |
| Legally qualified electronic signature | Not implemented for Estimates; current controls retain decision evidence and explicitly disclaim legal-signature validity. |
| Live card/ACH collection, payment links, fees, settlement, payout, chargeback, live refund | Provider gate; the retained processor adapter fails closed. |
| Automatic native/QBO journal posting and reconciliation | Governance seam exists, but the qualified receipts remain `not_posted`; no posting is inferred. |

## Qualification evidence

- Ruff: pass, zero findings across `backend`.
- Ruff format: pass, 1,660 files checked.
- MyPy: pass, zero findings across 1,040 source files.
- Focused PostgreSQL/Redis backend suite: 159 passed; zero failed; disposable
  PostgreSQL 16 and Redis 7 cleanup verified. Thirty existing SQLAlchemy
  transaction-cleanup warnings remain non-failing.
- Migration lifecycle: fresh upgrade to `y4z6b8d0f2h5`, single head, no
  autogenerate drift; downgrade logic fails closed around retained
  expanded-method evidence.
- Frontend production build: pass under pinned Node 24.22.3.
- Frontend dependency audit: zero vulnerabilities.
- Revenue-focused frontend: 24 passed; zero failed.
- Full frontend run: 800 passed, 7 failed. All seven are the pre-existing
  `FinancialReportsRoute.test.tsx` stale mock omission of
  `useQboHistoricalCatalog`; neither that test nor the QBO archive hook is
  changed by this branch. This is not a revenue-cycle regression.
- Assembled application acceptance: pass, including protected-principal
  authentication, authorization, tenant isolation, restricted database
  identity, service restart/readback, and backup/isolated restore of 429 public
  tables.
- Authenticated responsive browser: 3/3 pass (desktop, tablet, mobile).

## Integration and rollback

Laptop Master should integrate the published branch without squashing away the
migration, verify that `y4z6b8d0f2h5` is the sole descendant of the then-current
head, and rerun the candidate-specific assembled gate with
`REVENUE_CYCLE_ACCEPTANCE=true`. Rollback is application-first, followed by the
migration downgrade only when no `cash`, `ach_external`, or `card_external`
manual-payment evidence exists. If such evidence exists, the downgrade must
remain blocked until Finance supplies an explicit, non-destructive successor
plan.

No deployment is authorized by this handoff.

## Exact external and owner gates

1. Select and contract an approved merchant processor and merchant account;
   authorize test-mode credential/webhook custody and the card/ACH/payment-link
   methods to admit.
2. Approve provider-specific settlement, fee, payout, dispute, refund,
   reconciliation, and duplicate/replay contracts before live collection.
3. Select an authorized e-sign/customer-communication mechanism and approve the
   legal acceptance, document-retention, and delivery policy.
4. Owner/accountant approval remains required for real All County tax,
   discounts, active prices, residential/commercial terms, deposit/progress
   schedules, credit/refund policy, and Accounting/QBO mappings.

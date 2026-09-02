# Revenue Cycle Operational Product 1 — protected integration packet

## Authority and scope

- Starting protected authority: `fd2af4057a8dc1ba14777e3c052dd6ed39656404`.
- Source branch: `work/revenue-cycle-operational-product-1`.
- Scope: native Invoice office projection, deterministic AR aging, Customer balance projection, truthful Payment evidence language, and responsive office presentation.
- No real Payment, refund, Customer communication, Accounting posting, QBO/HCP mutation, Preview deployment, or Production action occurred.

## Capability audit

| Capability | Classification | Authoritative evidence / remaining gate |
| --- | --- | --- |
| Invoice create, issue, detail, accepted Estimate snapshot | PRODUCT_READY | Native versioned Invoice service; completed Job and accepted revision checks; immutable calculation digest. |
| Invoice office directory, open AR, deterministic aging | PRODUCT_READY | Bounded Company/Branch-scoped workspace with Customer/Job/Location search and explicit as-of date. |
| Customer balance | PRODUCT_READY | Native Invoice/AR ledger/Payment-receipt projection; source history is not blended. |
| Credits, write-offs, void/application reversal | ENGINEERING_READY | Append-only, versioned, audited authority exists; owner reason/policy and finer permission separation remain required. |
| Payment evidence and application | ENGINEERING_READY | Provider-neutral capture evidence, available balance, idempotent application, over-application/replay protection. |
| Provider collection, settlement, deposits, refunds, disputes | PROVIDER_REQUIRED | Canonical seams and deterministic fake provider exist; real provider/merchant authority is absent by design. |
| Payment request/link | PROVIDER_REQUIRED | No authoritative Customer-facing request/session product; a request must remain distinct from Payment. |
| Invoice/receipt delivery | PROVIDER_REQUIRED | Communications delivery evidence exists, but no Invoice/receipt template and provider binding is admitted. |
| Customer receipt document | PARTIAL | Payment receipt evidence is inspectable; Customer-facing receipt artifact/delivery authority is not complete. |
| Native Customer statement | PARTIAL | Native balance facts are sufficient; statement artifact/version/delivery contract is not authoritative. |
| Corrections | ENGINEERING_READY | Successor/correction event authority exists; office successor workflow needs policy/product completion. |
| Dispute/collection hold | POLICY_REQUIRED | Payment dispute evidence exists; Invoice collection-hold policy is not authoritative. |
| Accounting handoff | ENGINEERING_READY | Posting receipt and reconciliation-required states exist; no Accounting posting was performed here. |
| Migration historical AR | SOURCE_REQUIRED | Migration owns admission. Conflicted/unadmitted evidence remains explicit and is never reported as native zero. |
| Beacon/Luminary/LIA/Economics composition | ENGINEERING_READY | Existing read-only evidence planes distinguish earned work, Invoice, AR, Payment, settlement, and cash. New workspace publishes deterministic attention reasons without creating signal lifecycle authority. |

## Product changes

- `GET /api/v1/invoices/workspace`: bounded server-side Invoice/AR directory; explicit cutoff; open, overdue, attention, and lifecycle views; authorized Branch filter; Customer/Invoice/Job search; deterministic aging buckets; no amount-based prioritization.
- `GET /api/v1/invoices/{invoice_id}/office-detail`: scoped Customer, Service Location, Job, Estimate source, terms, due state, Accounting readiness, and last AR evidence.
- `GET /api/v1/invoices/customers/{customer_id}/balance`: native Invoice total/open balance, credit, write-off, applied Payment, unapplied receipt, dispute, and legacy-evidence completeness.
- Responsive Invoice list/detail presentation with attention reasons and explicit native-only truth language.
- Payment and Customer-context copy no longer labels provider capture assertions as cash or settlement.

## Security and contract properties

- Every projection requires `COMPANY_INVOICE_READ`, scopes by authenticated Company and authorized Branch IDs, and conceals foreign objects with the existing safe 404 contract.
- Search is bounded to 160 characters; pagination is capped at 200; queries use indexed Company/Branch/Customer/due-date identities and aggregate related evidence without per-row database calls.
- Existing mutation permissions, versions, idempotency, immutable AR ledger, accounting receipt, event, provider, and Migration boundaries are unchanged.
- The field/mobile contract is unchanged; it receives no Company-wide AR or Accounting authority.

## Integration procedure

1. Require the source branch to be rebased/merged only by Enterprise against the protected authority recorded in the final report.
2. Review the three additive read endpoints and frontend office presentation.
3. Run Alembic head verification (no new revision), affected backend PostgreSQL suites, frontend tests/lint/build, and protected-data scan.
4. Deploy only through Enterprise Preview authority. This branch does not deploy.

## External and owner gates

- Select/admit a real payment provider and merchant account; define card/ACH token, webhook, uncertainty, retry, settlement, refund, and receipt contracts.
- Approve credit, write-off, correction, dispute/hold, collections, terms/credit-policy, statement, receipt, and delivery policy.
- Split adjustment execution into finer credit/write-off permissions before broad office delegation.
- Admit historical financial source authority through Migration; unresolved source conflict, opening balances, Undeposited Funds control, and COA mapping gaps remain unavailable—not zero.

# QBO Accounting Evidence UI — Enterprise integration packet

## Candidate boundary

This candidate adds a read-only QuickBooks Online source-evidence projection to
the existing `/financial-reports` navigation destination. Native ACP Accounting
statements remain in their own section and continue to derive exclusively from
posted ACP General Ledger entries.

The UI proposes this company-scoped, report-read-authorized projection endpoint
for final reconciliation with OM1 ECO:

`GET /api/v1/accounting/source-evidence/qbo?basis=cash|accrual`

`frontend/src/api/qboAccountingEvidence.ts` is a clearly labeled consumer
projection, not yet an authoritative ECO HTTP contract. It composes the accepted
`qbo-om2b-source-evidence/v1` packet fields with the still-required bounded row
projections: explicit accounting basis, source as-of/acquisition time, refresh
state, sealed snapshot identity/digest, limitations, nullable amount evidence,
accounts, Invoice/AR, bills/AP, payment/application evidence, cross-source
conflicts, and available reports. `mutation_authority` must equal `none`.

OM1 ECO candidate `ecfada3984beb8298b68c2df0d7a200c07a084a5` supplies the
packet authority but not this HTTP/row projection. Preview currently returns
`404` for the proposed endpoint. Enterprise must not deploy or describe this UI
as live/agreed until ECO publishes or explicitly accepts a compatible endpoint.

## Truth and safety invariants

- QBO is authoritative only for what the verified source snapshot reported.
- A null or unavailable amount is rendered as `Unavailable`, never zero.
- Snapshot acquisition time is not represented as live synchronization.
- QBO balances are not labeled or aggregated as posted ACP ledger truth.
- HCP operational assertions and ACP native records are not added to QBO totals.
- Payment evidence does not assert settlement, money movement, or ACP posting.
- Cash/accrual basis is explicit in the request and response.
- Endpoint failure produces a bounded unavailable state and no substituted data.
- Access uses existing `COMPANY_ACCOUNTING_REPORT_READ`; the backend must enforce
  the same company-scoped authority independently.

## Enterprise sequence

1. Integrate the OM1 ECO packet candidate and its future compatible row endpoint.
2. Reconcile this UI commit onto the same protected-authority descendant.
3. Run the focused frontend tests, full ESLint, TypeScript, production build, and
   ECO backend contract/authorization/privacy tests.
4. In sanctioned Preview, verify cash and accrual snapshots against the same
   sealed source generation and confirm unavailable evidence remains unavailable.
5. Confirm native ACP statements are unchanged and QBO/HCP totals are never
   combined before deployed acceptance.

No QBO mutation, Accounting posting, Customer communication, Preview deployment,
or Production action is authorized by this packet.

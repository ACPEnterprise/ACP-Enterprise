# Full-history and Accounting-admission owner packet

This packet is bound to QBO bounded run `real-qbo-2026-08-31-g5`, cutoff
2026-08-31, and HCP master `63273602-8619-5c0b-8b49-8537338b04b5`.
It authorizes full available history, not Accounting posting, source mutation,
source freeze, or Production activation.

## Resolved decision

The selected window is **FULL AVAILABLE HISTORY**. Each family retains its own
actual coverage. Missing earlier family history is not fabricated. Independent
cutoff controls remain required wherever API transaction history does not prove
the ledger balance.

## Employee crosswalk cards

Source identities are represented only by safe SHA-256 evidence identities.
Candidate evidence combines sealed source identity, source/native identity,
tenant/Branch authority, and recorded historical assignments; it is not a
name-only match.

| Source digest | Candidate ACP Employee | Job assignments | Recommendation |
|---|---|---:|---|
| `4b242926...a9015` | `90749e79-32a3-56ec-bfd8-9456db0fe2cc` | 172 | Confirm candidate |
| `7ecff113...fb1b` | `7c106837-ddc4-5b26-ac8c-cd63fed6251a` | 1 | Confirm candidate after owner identity review |
| `b39b9262...ed51f` | `907fe2a4-c503-591c-81cd-4b7e7d05dbea` | 102 | Confirm candidate |
| `c9f09f51...a7335` | `d6b8602d-2f30-5b3e-abde-031ab7c6c135` | 27 | Confirm candidate |
| `cf4f845f...2880` | `5311f1a7-2346-54d6-a4be-155b48ced211` | 20 | Confirm candidate |
| `e023c0bb...19f0` | `60ef7cc3-08e8-556f-81f5-d75240bb8498` | 180 | Confirm candidate |
| `1aed48e8...578a` | none | 0 | Keep `EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS` |

The assignment count is the mechanically joined retained Job-assignment count.
It does not include unrelated source appearances and therefore does not replace
the sealed aggregate history evidence.

## Branch crosswalk

The single active rehearsal candidate is Branch
`887f413a-70dc-4ab1-98aa-8e84f4e7efd0`, Company
`3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd`. It is the primary `PLUMBING` Branch.
Owner confirmation remains required for the live target because a display label
is not identity. Confirmation unlocks the source Plumbing unit and the 277/278
selected open Jobs that previously lacked Business Unit evidence. Otherwise
those rows remain held.

## Exact cutoff controls

All reports use Accrual basis and cutoff 2026-08-31 unless stated otherwise.

| Gate | Required QBO evidence | Purpose |
|---|---|---|
| AR | A/R Aging Detail, Open Invoices, Trial Balance | Tie open items to AR control and resolve the post-cutoff-modified invoice |
| AP | A/P Aging Detail, Unpaid Bills, Trial Balance | Independently prove AP, including a genuine zero |
| Cash/bank | Balance Sheet, Trial Balance, per-account Account QuickReports | Prove each mapped cash/bank balance |
| Credit cards | Balance Sheet, Trial Balance, per-account Account QuickReports | Prove mapped card liabilities |
| Other liabilities/equity | Balance Sheet, Trial Balance, General Ledger | Prove classifications and cutoff balances |
| Inventory | Balance Sheet and Inventory Valuation Summary | Tie any financial inventory control balance |
| Payroll/tax liabilities | Balance Sheet, Trial Balance, General Ledger plus authoritative subledger evidence where applicable | Establish account authority and completeness |

The General Ledger date range is the full available history through 2026-08-31.
Account QuickReports cover the same period for each mapped bank and credit-card
account. These reports are controls, not loader rows.

## Remaining decisions in priority order

1. Approve the 130-account mapping packet, especially every
   `OWNER_FINANCE_DECISION`, `UNSUPPORTED`, or `CONFLICTING` row.
2. Supply/register the cutoff control reports above. This unlocks AR/AP/cash and
   other balance admission.
3. For the pre-cutoff Invoice modified after cutoff, choose current corrected
   source truth (recommended, with correction lineage) or separately substantiate
   the historical cutoff version. Never silently rewrite G5.
4. Confirm the six Employee candidates and retain the seventh exclusion.
5. Confirm the live Branch candidate or keep unmapped open work held.
6. Keep all 296 canceled-balance Jobs on HOLD unless explicit cross-provider
   identity plus Accounting controls corroborate or contradict the balance.
7. Retain the 24 unlinked Estimates as evidence-only unless authoritative Job
   relationship evidence appears.

After these controls and decisions are sealed, the supported next phase is:
Accounting source-authority admission, combined rehearsal replay, reconciliation,
then source-freeze/final-delta readiness. Source freeze and Production activation
remain separately gated.

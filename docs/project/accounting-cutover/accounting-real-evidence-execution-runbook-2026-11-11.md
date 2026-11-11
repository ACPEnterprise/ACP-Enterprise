# Accounting real-evidence execution runbook

Date: 2026-11-11

Authority: protected Accounting/QBO contracts at
`48f3911f20f8945f0fc183844363999e6d6c9d00`

Execution owner: Laptop MASTER / ENTERPRISE.RELEASE

This is a preparation packet. Do not run a command in a section marked
**AUTHORIZED BETA MUTATION** until Release has mounted the sealed evidence and
separately authorized the action. None of these procedures writes to QBO.

## Operator variables

Use an authenticated Beta session belonging to the exact All County Company.
Do not paste bearer tokens into shell history or evidence packets.

```bash
export ACP_API_BASE='https://<BETA-HOST>'
export ACP_SESSION_TOKEN='<EPHEMERAL-ACCOUNTING-OPERATOR-TOKEN>'
export ACP_AUTH_HEADER="Authorization: Bearer ${ACP_SESSION_TOKEN}"
export ACCOUNTING_CUTOFF='2026-08-31'
export PERIOD_START='2026-08-01'
export EXPECTED_QBO_REALM='<RELEASE-VERIFIED-ALL-COUNTY-REALM-ID>'
export QBO_PRODUCTION_EVIDENCE_ROOT='<RELEASE-MOUNTED-RESTRICTED-ROOT>'
```

Store each response in the Release evidence directory with mode `0700` on the
directory and `0600` on files. The examples below use `jq`; they do not display
OAuth credentials or source payloads.

## 1. Verify sealed Production evidence and realm — read only

From `backend/`, in the deployed application environment, run the repository's
canonical parser. This validates the complete manifest, bounded-manifest
digest, Production environment, snapshot identity, every envelope digest,
every raw-blob digest, and provider identity.

```bash
EXPECTED_QBO_REALM="$EXPECTED_QBO_REALM" \
QBO_PRODUCTION_EVIDENCE_ROOT="$QBO_PRODUCTION_EVIDENCE_ROOT" \
PYTHONPATH=. .venv/bin/python - <<'PY'
import json
import os
from pathlib import Path
from app.qbo_source.bounded_evidence import (
    BoundedEvidenceError,
    latest_bounded_evidence,
    load_bounded_envelopes,
)

root = Path(os.environ["QBO_PRODUCTION_EVIDENCE_ROOT"])
expected_realm = os.environ["EXPECTED_QBO_REALM"]
packet = latest_bounded_evidence(root)
if packet is None:
    raise SystemExit("FAIL: no complete bounded Production packet")
realm = str(packet.bounded_manifest["realm_id"])
if realm != expected_realm:
    raise SystemExit("FAIL: sealed packet realm does not match Release authority")
envelopes = load_bounded_envelopes(packet)
print(json.dumps({
    "result": "PASS",
    "environment": packet.bounded_manifest["environment"],
    "realm_id": realm,
    "run_id": packet.manifest["run_id"],
    "ended_at": packet.manifest["ended_at"],
    "accounting_date_cutoff": packet.bounded_manifest["accounting_date_cutoff"],
    "manifest_sha256": packet.manifest_sha256,
    "record_count": len(envelopes),
}, sort_keys=True))
PY
```

Then verify the application sees the same custody and authenticated Company:

```bash
curl --fail-with-body --silent --show-error \
  -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/accounting/source-evidence/qbo/native-application" \
  | tee qbo-preflight-ledger.json | jq '{source_evidence,last_execution}'
```

Stop if `available` is not `true`, the manifest digest/run differs, the realm
differs, the Company binding fails, or any digest validation fails.

## 2. QBO preflight — read only

```bash
curl --fail-with-body --silent --show-error \
  -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/accounting/source-evidence/qbo?basis=cash" \
  > qbo-source-workspace-cash.json

curl --fail-with-body --silent --show-error \
  -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/accounting/source-evidence/qbo/native-application/review-queue?limit=500" \
  > qbo-review-queue-before.json

jq '{source_evidence,families,last_execution}' qbo-preflight-ledger.json
jq '{open_items:(.items|length),by_family:(.items|group_by(.source_family)|map({family:.[0].source_family,count:length}))}' \
  qbo-review-queue-before.json
```

Release must also prove deployed schema `current=head`, one Alembic head, and
zero drift before application. Preflight fails closed; do not substitute a
partial acquisition or another realm.

## 3. Apply safe majority — AUTHORIZED BETA MUTATION

This calls ACP only. It processes sealed envelopes independently, applies or
binds deterministic records, quarantines true conflicts, and records explicit
unsupported/provider-unavailable dispositions. It performs no QBO write and no
Accounting posting. Retry after a lost response is idempotent.

```bash
curl --fail-with-body --silent --show-error --request POST \
  -H "$ACP_AUTH_HEADER" \
  -H 'Content-Type: application/json' \
  "$ACP_API_BASE/api/v1/accounting/source-evidence/qbo/native-application" \
  | tee qbo-safe-majority-receipt.json

jq '{classification,source_run_id,source_manifest_sha256,processed,created,replayed,families,qbo_write_performed,accounting_posting_performed}' \
  qbo-safe-majority-receipt.json
```

Require `qbo_write_performed=false`, `accounting_posting_performed=false`, and
`unexplained=0` for every family or a named engineering defect. Retain the full
receipt and SHA-256 it outside the application tree.

## 4. Produce the quarantined Finance queue — read only

```bash
curl --fail-with-body --silent --show-error \
  -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/accounting/source-evidence/qbo/native-application/review-queue?limit=500" \
  > qbo-finance-review-queue.json

jq '[.items[] | {
  id,source_family,provider_record_id,provider_version,reference_number,
  source_date,source_amount,source_entity_names,exact_conflict,
  conflicting_fields,candidate_native_ids,affected_dependents,
  allowed_actions,current_decision,state,unlocks
}]' qbo-finance-review-queue.json > qbo-finance-decision-queue.json
```

No decision is made by this command. Resolution uses the existing decision
endpoint and requires the authority shown on each allowed action.

## 5. Opening-control projection

Release first obtains `package_identity` from the sealed package manifest. The
preview is read-only and accepts no client-calculated balances.

```bash
export OPENING_PACKAGE_IDENTITY='<SEALED-PACKAGE-IDENTITY>'
curl --fail-with-body --silent --show-error --request POST \
  -H "$ACP_AUTH_HEADER" -H 'Content-Type: application/json' \
  --data "{\"package_identity\":\"$OPENING_PACKAGE_IDENTITY\"}" \
  "$ACP_API_BASE/api/v1/accounting/opening-controls/sealed-preview" \
  | tee opening-control-preview.json

jq '{package_identity,cutoff_at,total_debits,total_credits,balanced,
     ar_control_balance,ar_subledger_balance,ar_difference,
     ap_control_balance,ap_subledger_balance,ap_difference,
     balance_sheet_equation_supported,unexplained_equity,status,
     evidence_digest,exceptions}' opening-control-preview.json
```

Submitting the preview into the durable review lifecycle is an **AUTHORIZED
BETA MUTATION** and still does not post a journal:

```bash
curl --fail-with-body --silent --show-error --request POST \
  -H "$ACP_AUTH_HEADER" -H 'Content-Type: application/json' \
  --data "{\"package_identity\":\"$OPENING_PACKAGE_IDENTITY\"}" \
  "$ACP_API_BASE/api/v1/accounting/opening-controls/sealed" \
  | tee opening-control-submission.json
```

Do not call `/approve` or `/apply` until all exceptions are resolved, a distinct
authorized reviewer accepts the evidence digest, and an already-posted governed
opening journal exists. This runbook does not authorize that journal.

## 6. Bank/card prepare, review, Finance close

Repeat for each bank and credit-card account. First inspect account summaries,
transactions, unmatched items, statement preview, and history:

```bash
curl --fail-with-body --silent --show-error -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/accounting/banking/summary" > banking-summary.json
curl --fail-with-body --silent --show-error -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/accounting/banking/match-review?bank_account_id=$BANK_ACCOUNT_ID" \
  > "bank-$BANK_ACCOUNT_ID-match-review.json"
curl --fail-with-body --silent --show-error -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/accounting/banking/accounts/$BANK_ACCOUNT_ID/reconciliations/history" \
  > "bank-$BANK_ACCOUNT_ID-history.json"
```

Preview using statement evidence before mutation:

```bash
curl --fail-with-body --silent --show-error --request POST \
  -H "$ACP_AUTH_HEADER" -H 'Content-Type: application/json' \
  --data @bank-reconciliation-preview-request.json \
  "$ACP_API_BASE/api/v1/accounting/banking/accounts/$BANK_ACCOUNT_ID/reconciliations/preview" \
  | tee "bank-$BANK_ACCOUNT_ID-reconciliation-preview.json"
```

The request contains `statement_identity`, `period_start`, `period_end`, exact
`ending_balance`, and `cleared_transaction_ids`. Require `difference=0`,
`unresolved_exceptions=0`, and `can_close=true`.

The next three calls are **AUTHORIZED BETA MUTATIONS**. The preparer uses
Accounting Reconcile authority; submit preserves that actor; close requires a
different user with Finance Approve authority.

```bash
# Prepare: request includes statement identity/dates; ending, book, cleared and
# outstanding totals; cleared IDs; outstanding items; and statement provenance.
curl --fail-with-body --silent --show-error --request POST \
  -H "$ACP_AUTH_HEADER" -H 'Content-Type: application/json' \
  --data @bank-reconciliation-prepare-request.json \
  "$ACP_API_BASE/api/v1/accounting/banking/accounts/$BANK_ACCOUNT_ID/reconciliations/prepare" \
  | tee bank-reconciliation-prepared.json

export RECONCILIATION_ID="$(jq -r .id bank-reconciliation-prepared.json)"
export RECONCILIATION_VERSION="$(jq -r .version bank-reconciliation-prepared.json)"

curl --fail-with-body --silent --show-error --request POST \
  -H "$ACP_AUTH_HEADER" -H 'Content-Type: application/json' \
  --data "{\"expected_version\":$RECONCILIATION_VERSION}" \
  "$ACP_API_BASE/api/v1/accounting/banking/accounts/$BANK_ACCOUNT_ID/reconciliations/$RECONCILIATION_ID/submit" \
  | tee bank-reconciliation-submitted.json

# Replace ACP_AUTH_HEADER with the distinct Finance reviewer session.
export RECONCILIATION_VERSION="$(jq -r .version bank-reconciliation-submitted.json)"
curl --fail-with-body --silent --show-error --request POST \
  -H "$ACP_FINANCE_AUTH_HEADER" -H 'Content-Type: application/json' \
  --data "{\"expected_version\":$RECONCILIATION_VERSION}" \
  "$ACP_API_BASE/api/v1/accounting/banking/accounts/$BANK_ACCOUNT_ID/reconciliations/$RECONCILIATION_ID/close" \
  | tee bank-reconciliation-closed.json
```

## 7. Common-cutoff reports — read only

Use one cutoff, currency, Company scope, and approved basis. Native P&L is the
`income-statement` endpoint. AR is the native receivables summary plus bounded
open-workspace pages; AP aging is paginated.

```bash
curl --fail-with-body --silent --show-error -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/accounting/reports/trial-balance?as_of=$ACCOUNTING_CUTOFF" \
  > final-trial-balance.json
curl --fail-with-body --silent --show-error -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/accounting/reports/balance-sheet?as_of=$ACCOUNTING_CUTOFF" \
  > final-balance-sheet.json
curl --fail-with-body --silent --show-error -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/accounting/reports/income-statement?start_date=$PERIOD_START&end_date=$ACCOUNTING_CUTOFF" \
  > final-profit-and-loss.json
curl --fail-with-body --silent --show-error -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/invoices/receivables-summary?as_of=$ACCOUNTING_CUTOFF" \
  > final-ar-aging-summary.json
curl --fail-with-body --silent --show-error -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/invoices/workspace?as_of=$ACCOUNTING_CUTOFF&state=open&limit=200&offset=0" \
  > final-ar-aging-page-000.json
curl --fail-with-body --silent --show-error -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/accounts-payable/aging?as_of=$ACCOUNTING_CUTOFF&limit=200&offset=0" \
  > final-ap-aging-page-000.json
curl --fail-with-body --silent --show-error -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/accounting/banking/cash-flow?period_start=$PERIOD_START&period_end=$ACCOUNTING_CUTOFF&basis=posted_cash_movement" \
  > final-cash-flow.json
```

Continue AR/AP pagination until a page is shorter than its limit. Retain each
report's manifest, basis, scope, cutoff, checksum, quality and provenance. Then:

```bash
curl --fail-with-body --silent --show-error -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/accounting/periods/$PERIOD_ID/report-comparisons" \
  > final-report-comparisons.json
curl --fail-with-body --silent --show-error -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/accounting/accountant-review" \
  > final-accountant-review.json
```

Do not treat unavailable or incomplete values as zero.

## 8. First native period-close acceptance

Read-only gate:

```bash
curl --fail-with-body --silent --show-error -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/accounting/periods" > accounting-periods.json
curl --fail-with-body --silent --show-error -H "$ACP_AUTH_HEADER" \
  "$ACP_API_BASE/api/v1/accounting/periods/$PERIOD_ID/close-readiness" \
  | tee period-close-readiness.json
jq '{overall_readiness,required_approvals,blockers,evidence_digest,generated_at}' \
  period-close-readiness.json
```

Only `overall_readiness=READY`, zero unresolved blockers, accepted comparisons,
and the current readiness digest permit close. Begin-close and close are
**AUTHORIZED BETA MUTATIONS**:

```bash
export PERIOD_VERSION='<CURRENT-PERIOD-VERSION>'
curl --fail-with-body --silent --show-error --request POST \
  -H "$ACP_AUTH_HEADER" -H 'Content-Type: application/json' \
  --data "{\"expected_version\":$PERIOD_VERSION,\"reason\":\"Begin first native close after accepted cutover controls\"}" \
  "$ACP_API_BASE/api/v1/accounting/periods/$PERIOD_ID/begin-close" \
  | tee period-begin-close.json

export PERIOD_VERSION="$(jq -r .version period-begin-close.json)"
export READINESS_DIGEST="$(jq -r .evidence_digest period-close-readiness.json)"
curl --fail-with-body --silent --show-error --request POST \
  -H "$ACP_FINANCE_AUTH_HEADER" -H 'Content-Type: application/json' \
  --data "{\"expected_version\":$PERIOD_VERSION,\"reason\":\"Finance accepted common-cutoff controls\",\"readiness_digest\":\"$READINESS_DIGEST\"}" \
  "$ACP_API_BASE/api/v1/accounting/periods/$PERIOD_ID/close" \
  | tee period-closed.json
```

Close requires both Period Manage and Finance Approve. Refresh readiness after
any intervening change; stale digests fail closed.

## Decision packet A — owner

| Affected value/record | Existing evidence | Choices | Consequence | Operational blocker |
|---|---|---|---|---|
| Company reporting policy at cutover | All County historical policy is Cash; accepted Cash P&L covers 2022-01-01 through 2026-08-31 | Preserve Cash continuity; or document a future effective policy change | Preservation keeps source/report comparison coherent; a change requires a new effective policy and cannot rewrite history | Yes, until cutover basis/cutoff is approved |
| Common cutoff | Current control packet uses 2026-08-31 | Approve 2026-08-31; or select a newer fully evidenced common cutoff | A newer cutoff requires every report/control to be reacquired/reconciled consistently | Yes |
| 2026-08-18 Invoice with $850 source-version conflict | Aging shows $850 open; later TB, Open Invoices, Customer Balance Detail and GL support $0/current total $479,029.48 | Accept later source version; accept earlier aging version; or require transaction-audit evidence | Determines admitted AR/open item and the $850 variance; no silent selection | Blocks AR opening control, not unrelated safe-majority records |
| Legacy Undeposited Funds | No maintained historical control | Provide evidenced opening value; or approve not-applicable/start-native-at-cutover | Creates a controlled clearing opening or an explicit prospective boundary | Blocks opening control if a nonzero value is expected |
| Legacy inventory valuation | No maintained historical valuation | Provide physical quantity plus accepted cost basis; or approve not-applicable/start-native-at-cutover | Admits evidenced inventory or begins native valuation prospectively | Blocks inventory opening only; does not block unrelated Accounting |
| Cutover authorization | Application/review/close tooling is ready; real evidence has not been applied by this worker | Authorize Beta safe-majority rehearsal/application; defer | Authorization creates ACP application dispositions only; deferral leaves native Accounting source-incomplete | Yes for operational cutover |

## Decision packet B — accountant

| Affected value/account/record | Existing evidence | Choices | Consequence | Operational blocker |
|---|---|---|---|---|
| 130 QBO accounts, especially 92 `OWNER_ACCOUNTANT_DECISION` records | 38 mechanically classified; sealed decision queue will provide exact provider IDs/names/types | Approve proposed classification/control role; remap to an existing canonical classification; or hold with reason | Controls native statement grouping, posting policy and account usability | Each held account blocks dependent records; not the clean majority |
| Opening TB at 2026-08-31 | Corrected Cash TB balances at $1,283,400.24 debits/credits; transition Accrual TB on 2024-02-19 balances at $156,960.94 | Approve the selected sealed opening package; reject and request corrected evidence | Approval permits opening-control lifecycle; rejection prevents opening journal/application | Yes |
| Opening Balance Sheet/equity | Corrected Cash BS: assets $308,935.58; liabilities $464,078.66; equity -$155,143.08; delta $0 | Approve retained/current earnings classification; require supported reclassification; reject | Establishes equity/current-earnings treatment without a plug | Yes |
| AR control | Aging $479,879.48 versus later controls $479,029.48; exact $850 Invoice conflict above | Choose accepted version or request audit evidence | Resolves AR control-to-subledger tie | Yes for AR opening |
| AP control | AP Aging, Unpaid Bills and Vendor Balance Detail contain no numeric items | Confirm complete intended scope and $0 candidate; or require corrected/exported AP evidence | Confirms zero AP or retains AP as unavailable—not fabricated zero | Yes for AP opening |
| Each bank account and credit card | QBO activity is not an external statement balance; exact accounts appear in Banking summary after application | For each account approve statement ending balance and reconciling items; or hold for external statement | Permits Prepare → Review → Finance Close per account | Each unreconciled account blocks cash/card control and close |
| Undeposited Funds | Legacy control not maintained | Approve evidenced settlement-linked reconstruction; approve owner not-applicable boundary; or require external evidence | Controls clearing without treating deposits as revenue | Blocks clearing control where applicable |
| Payroll/tax and other liabilities | Provider history may be unavailable; no value may be inferred | Accept Payroll packet values; require provider/tax records; or mark an evidenced category not applicable | Establishes liabilities and due-date controls | Yes for affected liabilities and period close |
| First native period | Readiness endpoint binds exact current comparisons, review queue and digest | Accept and close; return blockers for correction; defer | Close freezes the governed period; return/defer leaves it open | Yes for first native close |

Exact account IDs, bank/card identities and provider record IDs must be copied
from `qbo-finance-decision-queue.json`, `banking-summary.json`, and the sealed
opening detail after mount. They are intentionally not guessed here.

## Decision packet C — Payroll inputs

| Affected input | Existing evidence | Choices | Consequence | Operational blocker |
|---|---|---|---|---|
| Payroll opening cutoff and covered periods | Accounting cutoff candidate is 2026-08-31; historical Payroll/tax detail may be provider-unavailable | Supply certified packet through cutoff; or explicitly hold unavailable periods | Defines what native Payroll liabilities/YTD can truthfully cover | Yes for Payroll reconciliation and close |
| Employee YTD gross, taxable wages and taxes by exact Employee identity | No values are admitted from unavailable QBO detail | Provide authoritative Payroll/provider register with Employee bindings; or mark source unavailable and defer | Enables YTD continuity; deferral prevents false YTD | Yes for Payroll YTD readiness; not unrelated Accounting |
| Employer and employee Payroll liabilities by agency/type | General source evidence does not establish exact payable balances | Provide certified balances and due dates; request accountant classification; or hold | Establishes liability control and remittance readiness without executing Payroll | Yes for affected liability accounts |
| Payroll clearing/cash account mapping | Among COA decisions until exact accounts are approved | Map exact evidenced accounts; or hold for accountant | Determines future Payroll Accounting posting targets | Yes for Payroll Accounting, not source application |
| Prior payments/remittances through cutoff | Must come from authoritative provider/bank/tax evidence | Supply evidence and reconcile; or retain provider-unavailable status | Prevents duplicate liabilities/remittances | Yes where an opening liability depends on payment history |
| Payroll run/control digest used by close | Existing API can project Payroll Accounting controls once a real run/evidence packet exists | Accept exact digest; reject discrepancies; or defer | Accepted digest satisfies period-close evidence; rejection keeps close blocked | Yes for first period close |

No item in this packet authorizes Payroll calculation, execution, tax filing,
remittance, Accounting posting, QBO writeback, or money movement.

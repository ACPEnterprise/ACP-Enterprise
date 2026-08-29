# QBO Development sandbox representative history

`MIGRATION.CONTINUOUS.PRODUCTION.12H.1` authorizes synthetic mutation only in
the already verified Intuit Development sandbox realm. The fixture service is a
separate, explicit mutation boundary; `IntuitReadOnlyAdapter` remains GET-only
and Production remains disabled.

## Sanctioned fixture command

The repository-owned entry point is:

```text
python -m app.qbo_source.sandbox_fixture qualify ...
python -m app.qbo_source.sandbox_fixture create ... --authorize-fixture-mutation
python -m app.qbo_source.sandbox_fixture controlled-change ... --authorize-fixture-mutation
```

The operator supplies the executing repository SHA and sanctioned actor, never
the realm, OAuth token, or client credential. The service obtains the realm from
the protected verified marker and rejects a non-sandbox connection, enabled QBO
Production runtime, mismatched realm, missing owner authorization flag, unsafe
destination, or contradictory fixture identity.

The deterministic fixture authority uses the reserved `ACP-QBO-QUAL-12H1` tag
and `ACP Qualification ...` names. It contains no real customer, vendor,
employee, or All County identity. Protected manifests live below the sandbox
runtime volume with directory mode `0700` and file mode `0600`; they retain
native IDs and payload digests but no OAuth material.

## Representative population

The fixture includes qualification-only accounts for cash, AR, AP, income,
COGS, expense, payroll, liability, fixed asset, depreciation, equity, credit
card, and undeposited funds. It includes two Customers, one Vendor, two Items,
Terms and Payment Method evidence, four Invoices, three Payments, one Credit
Memo, two Bills, one Bill Payment, one cash Purchase, one Vendor Credit, two
balanced Journal Entries, and one balance-sheet Transfer.

The independent expected-ledger manifest uses `Decimal` strings and proves AR
and AP roll-forwards, payment applications, partial residuals, customer/vendor
credits, balanced journals, transfer neutrality, and separation of opening
entries from operations. QBO Payment is never counted as revenue and Transfer
is never counted as income or expense.

## Acquisition and destination boundary

Creation responses are not migration evidence. After fixture creation, the
existing read-only adapter must query every supported family to pagination
exhaustion and seal content-addressed envelopes, page bodies, and manifests.
Version `qbo-source-transformation/v1` produces provider-neutral candidates
whose acceptance is always `source_evidence_only_unreconciled`; raw evidence is
preserved independently.

No fixture transformation selects real All County mappings or posts ACP
Accounting. Native destination reconnaissance validates reference, AR, AP,
Payment, Purchase, Journal, Transfer, currency, period, and lineage contracts.
Finance/Accounting acceptance remains a later separately authorized boundary.

## Replay, change, and cleanup

Identical fixture creation reuses the protected manifest and creates nothing.
Acquisition replay preserves provider-native identities and transformation
digests. The controlled-change command performs one sparse Customer metadata
update, preserves before/after digests, and never rewrites prior acquisition
evidence.

The representative dataset is intentionally retained for regression. Cleanup
is not automatic. A future cleanup command must remain sandbox-only, preserve
audit history, and use QBO-supported inactive/void/delete semantics without
touching Intuit defaults.

## Real-company and cutover gates

Development credentials, realm, evidence roots, and fixtures never qualify a
Production connection. Real-company acquisition requires separate owner OAuth,
exact Production realm and CompanyInfo verification, read-only scope, protected
Production credentials/evidence roots, and a separately authorized acquisition
run. Production access, migration persistence, posting, and cutover remain
prohibited by this contract.

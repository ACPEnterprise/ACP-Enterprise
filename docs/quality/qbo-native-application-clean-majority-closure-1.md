# QBO native application clean-majority closure

## Authority and boundary

This candidate started from `origin/integration/om2-operations` at
`b531aea65586366eef93819a9156a25e27bd7e00`. It consumes the latest complete,
digest-verified Production bounded snapshot already present in
`QBO_PRODUCTION_EVIDENCE_ROOT`. It performs no provider acquisition, QBO mutation,
Accounting posting, payment, Payroll execution, or tax action.

## Canonical application contract

`POST /api/v1/accounting/source-evidence/qbo/native-application` requires current
`COMPANY_ACCOUNTING_RECONCILE` authority and processes every sealed source envelope
independently. Exact existing provider identities may become `BOUND`. A record that
requires identity, account, transaction-semantics, or control evidence becomes
`QUARANTINED` without stopping another record. Unsupported and provider-unavailable
families receive explicit terminal dispositions. Exact replay creates no duplicate
ledger or review records.

The append-only application ledger preserves Company, Branch where applicable, QBO
realm, family, provider ID/version, acquisition and source timestamps, source and
evidence digests, dependency identities, native identity, match basis, actor, reason,
and supersession lineage. A changed payload under the same provider version is a
conflict; it never overwrites prior evidence.

`GET /api/v1/accounting/source-evidence/qbo/native-application` returns current
per-family disposition counts and safe-majority percentage. `GET
/api/v1/accounting/source-evidence/qbo/native-application/review-queue` returns
human-readable open conflicts without requiring raw JSON.

## Deployment execution

After Enterprise integration and schema migration to `q7s9u1w3y5a7`, an authorized
Accounting reconciler executes the POST once in Twelve Hats Beta. The response is the
controlling per-family count packet and must be retained with the protected release
evidence. Retry is safe if the response is lost.

Before execution, Release verifies:

1. the configured ACP Company equals the authenticated Company;
2. the evidence root is the restricted Production evidence volume;
3. the latest bounded manifest is complete and all blob/envelope digests pass;
4. the schema is current with one Alembic head;
5. no QBO write credential or posting command is involved.

The known `$850` A/R source-version conflict, unresolved account classifications,
missing bank/card reconciliation, AP zero-candidate confirmation, and unavailable
Payroll/tax detail remain local review/provider dispositions. They do not globally
block unrelated exact bindings.

## Remaining governed decisions

- Accountant: approve unresolved Chart-of-Accounts classifications.
- Accountant: confirm the AP zero candidate using the required QBO controls.
- Owner/accountant: resolve the `$850` A/R source-version conflict.
- Accountant/provider evidence: provide external bank/card reconciliation where
  admission depends on it.
- Payroll/tax owners: handle provider-unavailable historical detail under their
  separate authorities.

The application endpoint cannot infer any of these decisions.

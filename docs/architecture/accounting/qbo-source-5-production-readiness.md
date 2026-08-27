# QBO.SOURCE.5 — Production read-only acquisition readiness

This milestone reuses the proven Intuit authorization-code flow for a real QBO
source connection while keeping it physically separate from Development sandbox
state. It does not authorize or perform a real-company connection or extraction.

## Production control boundary

The non-Production ACP Preview control plane exposes the exact callback
`https://preview.allcountyhomeservices.com/api/v1/integrations/qbo/production/oauth/callback`.
Production Intuit credentials, rotating tokens, single-use state, exact expected
CompanyInfo name, connection marker, diagnostics, and evidence use dedicated
`/var/lib/acp-qbo-production` and `/var/lib/acp-qbo-production-evidence` volumes.
They never fall back to `/var/lib/acp-qbo-sandbox`. ACP Production cannot enable
this control runtime.

The runtime stays disabled until Intuit Production approval, exact redirect
registration, protected Production client credential provisioning, and protected
owner-supplied expected CompanyInfo name are all complete. The owner then uses the
authenticated `COMPANY_ADMINISTER` initiation boundary and selects the real All
County company in Intuit. Callback processing is state-bound, exchanges the code
only with Production credentials, binds the returned realm, requests CompanyInfo
through that exact realm, and requires an exact CompanyName match. Mismatch deletes
temporary tokens and fails closed. Connection does not itself authorize extraction.

## Read-only snapshot

The implemented scope is exactly the existing `EntityKind` catalog: CompanyInfo,
Account, Customer, Vendor, Invoice, Payment, CreditMemo, Bill, BillPayment,
VendorCredit, Purchase, CreditCardPayment, Deposit, Transfer, JournalEntry,
TaxPayment, TaxAgency, Class, Department, Item, Employee, TimeActivity,
RefundReceipt, SalesReceipt, Estimate, and PurchaseOrder. Unsupported company or
locale entities produce an explicit partial run; absence is never fabricated.

The transport permits GET only on QBO Accounting API hosts. POST is permitted only
to Intuit OAuth token and revocation infrastructure. Every acquisition begins with
realm-scoped CompanyInfo verification. Queries use ordered `STARTPOSITION` and
`MAXRESULTS` pages up to 1,000, stop only on a short page, record each response
digest/request ID/count/start position, and use bounded deterministic retry.

Raw pages and canonical native payloads are content-addressed outside Git. Native
IDs, SyncTokens, relationships, timestamps, currency, status, accounting meaning,
and raw SHA-256 remain immutable. The sealed deterministic manifest records entity
counts, page evidence, snapshot/cutoff identity, start/end timestamps, and explicit
partial failure. No Enterprise accounting table is written.

After a separately authorized connection and extraction decision, the approved OM1
operator runs, inside the protected Preview backend runtime:

```text
python -m app.qbo_source.production --run-id <owner-approved-run-id> --cutoff <YYYY-MM-DD>
```

The command first re-verifies the protected marker, realm-bound token, exact company
name, and CompanyInfo. It then performs the bounded inventory/acquisition and emits
only safe run state, count, manifest digest, and failure code. The sealed manifest
feeds reconciliation and later ACC.MIG transformation under separate authority.

## External owner gate

1. Complete Intuit Production app review/questionnaire and obtain Production keys.
2. Register the exact Production redirect URI above in Intuit; no wildcard.
3. Provision the Production client ID/secret directly into the protected
   `qbo-production/client` namespace without chat, Git, environment dumps, or logs.
4. Place the exact real `CompanyInfo.CompanyName` in the protected Production
   configuration namespace; do not guess, trim, normalize, or paste it into chat.
5. Enable only the Preview Production-source control runtime and verify its empty
   token/state/connection stores and restricted evidence root.
6. Separately authorize one browser connection, select only the real All County QBO
   company, and stop after exact CompanyInfo verification.
7. Separately authorize the acquisition command with cutoff, custodian, evidence
   root/retention, and entity scope. Import remains a later gate.

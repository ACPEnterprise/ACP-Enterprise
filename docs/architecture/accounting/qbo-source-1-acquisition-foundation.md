<!-- markdownlint-disable MD013 -->

# QBO.SOURCE.1 — Source-Faithful QuickBooks Online Acquisition Foundation

## 1. Decision and scope

QuickBooks Online (QBO) is authoritative for **what QBO reported**, not automatically for final accepted accounting truth. Acquisition is read-only and preserves native records, links, classifications, balances, statuses, omissions, and conflicts as observed. It never closes an invoice, creates a payment or bill, reclassifies an AMEX purchase, redesigns an account, resolves a QBO/HCP conflict, or substitutes zero for absent evidence.

This milestone supplies provider-neutral contracts, deterministic synthetic fakes, reconciliation result types, and the owner connection runbook. It does not contain an Intuit client, credentials, real data, an ACP loader, persistence migration, Preview/Production change, or authentication attempt.

The runtime boundary is `backend/app/qbo_source/**`. `SourceAcquisitionProvider` exposes only `acquire`; there is deliberately no create, update, delete, void, or QBO report-adjustment method. Raw evidence is stored by a future protected evidence-store adapter outside Git; normalized envelope fields are indexes over, never replacements for, the raw JSON.

## 2. Official authorization architecture

Use an Intuit Developer app and OAuth 2.0 authorization-code flow. QBO does not support a useful narrower accounting read-only scope: request only `com.intuit.quickbooks.accounting`; do not request Payments, Payroll, OpenID/profile, email, phone, or address scopes unless a later separately approved requirement proves them necessary. The accounting scope technically permits writes, so ACP enforces read-only behavior structurally through an acquisition-only adapter, egress allow-list (`GET` and QBO query/report calls only), and separate app/credential purpose.

1. Register an app in the Intuit Developer Dashboard and enable QuickBooks Online Accounting.
2. Configure an exact HTTPS redirect URI. Use a loopback/local redirect only where Intuit permits it for development. Redirect URIs, client IDs, and environment identity are configuration; client secrets and tokens are secret material.
3. Generate a cryptographically random, single-use `state`, store it server-side with expiry, and redirect the owner to `https://appcenter.intuit.com/connect/oauth2` with `client_id`, `response_type=code`, the exact redirect URI, scope, and state.
4. The owner signs in to Intuit, selects the intended QBO company, reviews the app permissions, and selects **Connect**. The callback returns `code`, `state`, and `realmId`. Reject state mismatch, reuse, expiry, missing realm, or an unexpected realm/environment.
5. Exchange the one-time code server-to-server at `https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer` using the app credentials. Never put a client secret or token in a browser, command argument, prompt, URL, log, exception, trace, fixture, documentation, or Git.
6. Call `CompanyInfo/{realmId}` and require the owner-approved realm/company identity before any enumeration. Persist the realm binding independently of display name.

Official references: [Intuit authentication and authorization](https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization), [OAuth 2.0](https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0), and [Intuit OAuth FAQ](https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/faq).

### Token lifecycle, storage, refresh, and revocation

- Access tokens are short-lived (currently 60 minutes). Refresh tokens use Intuit's rolling lifecycle (currently 100 days of inactivity). Treat these values as provider configuration verified from official documentation at implementation time, not hard-coded accounting assumptions.
- Each successful refresh can rotate the refresh token. Atomically store the complete newest token response before concurrent workers can refresh; serialize refresh per realm/app; retain the immediately prior encrypted version only for controlled recovery within Intuit's documented grace behavior; never overwrite a usable token with a failed response.
- Store app secret and encrypted token material in an approved secrets manager/KMS outside the database/Git. Store only a secret reference, realm, app/environment identity, scopes, issued/expiry times, rotation generation, and redacted token fingerprint in operational state. Restrict decrypt/use to the acquisition workload and audit access without token values.
- Refresh only shortly before expiry with deterministic single-flight behavior. `invalid_grant`, realm mismatch, revoked consent, expired refresh, or changed scope stops acquisition and requires owner reconnection; it never falls back to another company.
- Owner revocation is available from Intuit account **Sign-in & security → Apps with access to your account** (wording may vary), and the app can call Intuit's revoke endpoint for its current token. Revocation deletes/cryptographically destroys local token material while retaining non-secret audit evidence. See [Intuit revoke tokens](https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0#revoke-access-token).

### Sandbox and real-company separation

Use separate Intuit Development and Production credentials, redirect URIs, secret paths, storage namespaces, allow-lists, realm bindings, and audit streams. A snapshot identity includes `environment`; cross-environment token or realm use fails closed. Synthetic tests use neither. Enabling Production keys does not authorize connecting or acquiring from the real company.

## 3. API execution contract

- Pin and record an explicit `minorversion` on every request and in `SnapshotIdentity`. Upgrade only through fixture/contract/reconciliation review. Preserve QBO response metadata and native `SyncToken`. [Intuit minor versions](https://developer.intuit.com/app/developer/qbo/docs/learn/rest-api-features#minor-versions).
- Enumerate in a fixed entity order and native-ID order where QBO query support permits. Use `STARTPOSITION`/`MAXRESULTS`, with at most 1,000 rows per page, recording query text, page ordinal, returned count, request ID, start/end time, and response digest. Continue until a short/empty page. Reject repeated pages/IDs and unexplained count drift. [Intuit data queries](https://developer.intuit.com/app/developer/qbo/docs/learn/explore-the-quickbooks-online-api/data-queries).
- Budget below Intuit's published limits (currently 500 requests/minute per realm and 10 concurrent requests per realm), with one lower local concurrency cap. Honor `Retry-After`. Rate-limit responses and transient `408`, `429`, and `5xx` failures retry with capped exponential backoff plus deterministic jitter derived from snapshot/request identity. Network ambiguity retries the identical read. Authentication, authorization, validation, realm mismatch, and non-transient `4xx` errors do not retry. Record attempts without payloads or secrets. [Intuit API limits](https://developer.intuit.com/app/developer/qbo/docs/learn/rest-api-features#limits-and-throttles).
- Every page is raw-digested before parsing. Page/envelope writes to protected evidence storage are create-only. A duplicate evidence key must have the same digest; a different digest is a source-drift exception.

## 4. Native source coverage

Acquire every applicable supported native entity actually present, not a fabricated checklist row. The initial contract names: `CompanyInfo`, `Account`, `Customer`, `Vendor`, `Invoice`, `Payment`, `CreditMemo`, `Bill`, `BillPayment`, `VendorCredit`, `Purchase`, `CreditCardPayment`, `Deposit`, `Transfer`, `JournalEntry`, `TaxPayment`, `TaxAgency`, `Class`, `Department`, `Item`, `Employee`, `TimeActivity`, `RefundReceipt`, `SalesReceipt`, `Estimate`, and `PurchaseOrder`.

Preserve embedded and referenced `LinkedTxn`, line-level account/item/customer/class/department references, payment/deposit applications, currency/exchange fields, TxnDate, metadata timestamps, document/reference numbers, private/customer memos, status/active/void state, balances, and sparse fields exactly as returned. `Account` records identify bank, cash, Undeposited Funds, credit-card/AMEX, loan/liability, fixed-asset, depreciation, equity, and retained-earnings accounts; transactions and journal lines provide their accounting activity. Do not manufacture separate entities where QBO models these as account types or lines.

QBO `Purchase` is the principal native entity for expenses paid by cash, check, or credit card; `PaymentType`, `AccountRef`, and lines determine its reported meaning. Bills/AP exist only when native `Bill`/related records exist. An observed zero/minimal AP remains zero/minimal.

### Known unavailable or limited evidence

- The Accounting API is not a native QBO backup and does not expose every UI/internal object. Bank-feed downloaded/pending/review-state details and an issuer's statement posting date may be unavailable after a transaction becomes a posted QBO accounting entity.
- Detailed QBO Payroll data is not generally available through the Accounting API merely from the accounting scope. Acquire only API-supported Employee/TimeActivity and booked payroll journal/liability/account evidence; obtain payroll reports/provider evidence separately under explicit sensitive-data authority. Do not synthesize payroll detail.
- Sales-tax behavior varies by QBO locale and automated-sales-tax configuration. Preserve supported tax agencies, tax codes/rates/details, tax payments, transaction tax fields, liability accounts, and control reports; record unsupported calculated/UI evidence as a limitation.
- Inventory, fixed assets, loans, equity, retained earnings, bank/cash, Undeposited Funds, and AMEX are primarily represented by accounts plus supported transactions/journal lines, not necessarily dedicated API entities.
- Deleted entities and historical versions are not guaranteed by ordinary current-state queries. CDC is limited by Intuit's supported entity set and lookback window; webhooks are change notifications, not archive evidence. A first acquisition cannot reconstruct changes already outside available history.
- QBO reports can embody QBO-only report logic, preferences, localization, rounding, and computed groupings not reproducible from entity queries alone. Therefore control reports remain independent immutable evidence and differences remain exceptions.

The authoritative entity catalog and schemas must be rechecked before a real adapter is implemented: [QBO Accounting API entities](https://developer.intuit.com/app/developer/qbo/docs/learn/learn-basic-bookkeeping/quickbooks-online-accounting-api-entities) and [API explorer](https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/account).

## 5. Immutable source envelope

`QboSourceEnvelope` (`qbo-source-envelope/v1`) contains provider; realm, sandbox/production environment, snapshot and cutoff identity; native type and ID; `SyncToken`; native create/update timestamps; UTC acquisition time; canonical raw SHA-256; relationship identities; currency; source status; lossless source-accounting-meaning indexes; and the raw native JSON. Construction recalculates the digest and freezes mappings.

Protected evidence storage outside Git retains the original HTTP response bytes, response headers needed for provenance, page manifest, envelope JSON, hashes, and access/audit/retention evidence. It must use encryption, least privilege, immutability/object lock where available, versioned retention, backup/readability checks, and deletion authority. Git may contain schemas, code, and explicitly synthetic fixtures only.

Technical normalization may standardize timestamps, identifiers, decimal strings, and relationship indexes, but never changes the raw value or financial interpretation. QBO and HCP assertions occupy distinct source namespaces and can coexist.

## 6. Snapshot and cutoff semantics

The owner control package uses an **August 25, 2026 accrual accounting-date cutoff**. The exact QBO report end date, company timezone, report basis, filters, columns, currency, aging date/buckets, and export timestamps must be captured from the reports; absent metadata is an exception, never assumed.

QBO offers a live mutable API, not a transactional point-in-time snapshot across all endpoints. Therefore a source snapshot is an evidence interval:

1. bind realm and `CompanyInfo`, record UTC start/high-water time, cutoff date/timezone, basis, minor version, query plan, and requested kinds;
2. collect full current-state entities deterministically, retaining all returned records and marking accounting-date inclusion separately (`TxnDate <= 2026-08-25`), never deleting post-cutoff or later-edited evidence;
3. record native `MetaData` and `SyncToken`; collect supported CDC/change evidence around the interval;
4. repeat identity/version inventory at the end. Any entity created, updated, deleted, or drifting during the interval is explicit snapshot drift requiring deterministic re-run or disposition;
5. seal a manifest only when completeness checks pass. Record UTC end/high-water time and manifest digest.

`TxnDate <= cutoff` is not proof that the record existed at cutoff, and an update after cutoff may change an earlier-dated transaction. If QBO was not frozen at the report export instant, exact historical reconstruction may be impossible; state that limitation and reconcile it. Never backdate the acquisition timestamp or silently select a convenient version.

## 7. Control-report reconciliation

The owner-exported reports are immutable `control_report` artifacts with raw-byte digest and report metadata. Reconciliation uses exact decimals and named keys, never writes source envelopes, and emits `matched`, `exception`, `missing_source_evidence`, or `missing_control_evidence`. Missing is distinct from zero. Every result references native source evidence IDs and the control digest.

| Acquired evidence | August 25 control | Deterministic comparison |
|---|---|---|
| Journal-impacting transaction lines by account | Trial Balance | opening/activity/ending debit-credit balance by native account and total debits=credits |
| `Account` identity, parent, type/subtype, active state | Account List / COA | one-to-one native ID and reported attributes; no redesign |
| Invoice, Payment, CreditMemo and `LinkedTxn` open/application state | A/R Aging Detail; Customer Balance Detail; Open Invoices | customer/document identity, date/due date, original/open amount, application links, aging bucket and totals |
| Bill, BillPayment, VendorCredit and links | A/P Aging Detail; Vendor Balance Detail; Unpaid Bills | vendor/document identity, original/open amount, applications, aging bucket and totals; native absence remains absence |
| Revenue/expense transaction lines in report period | Profit & Loss | account/report grouping where evidenced, period activity, net income and report total |
| Asset/liability/equity transaction lines and balances | Balance Sheet | account balances, retained/current earnings presentation, assets=liabilities+equity and report total |

Report query parameters and QBO report-generated output may also be acquired as supporting native report evidence when the API supports the report, but they do not replace the independent owner exports. Rounding, report-only computation, unsupported fields, changed-after-export records, missing records, duplicate IDs, and any nonzero variance are exceptions with evidence and owner/Finance disposition status. No tolerance or materiality silently changes records.

## 8. AMEX / credit-card control domain

Identify AMEX by native QBO `Account` ID, name/masked number if QBO exposes it, account type/subtype, currency, parent, active status, and opening/closing balance evidence. Acquire all linked `Purchase` charges, credits/refunds/vendor credits where represented, `CreditCardPayment`, transfers/payments, journal entries, and fees/interest as QBO classified them. Preserve transaction date; API metadata timestamps; any available reference, payee/vendor, memo, amount, currency, account/category, class/department/customer/project references, and `LinkedTxn`.

Do not call the QBO transaction date an issuer posting date unless the source explicitly identifies it. Do not infer a job, material, vendor, AP bill, category, or corrected account from card behavior. Missing job/material attribution is later economic/reconciliation evidence. Future issuer-statement reconciliation is a separate source assertion keyed to the AMEX account and statement transaction; it does not mutate QBO evidence.

## 9. Source state, migration, and intelligence handoff

`SOURCE_REPORTED_STATE` is append-only evidence: source namespace, realm, native identity/version, raw digest, native status/classification/links, snapshot/cutoff, and reconciliation exceptions. `ENTERPRISE_ACCEPTED_STATE` is a separately authorized accounting outcome with its own effective date, approval, journal/correction identity, and lineage back to source evidence. It may disagree; it never overwrites the envelope.

`ACC.MIG.1` consumes only a sealed source manifest plus explicit Finance dispositions/mappings through `OpeningStateTransformer`. It records envelope/manifest digests on every proposed opening record. The existing rollback-only rehearsal and replay controls remain in force. Import, a real-data rehearsal, and target persistence are separately gated. Post-import corrections use Accounting's append-only reversal/replacement/reclassification mechanisms, not migration rewrites.

Evidence consumers receive facts, not authority:

- Business Economics may identify economic incompleteness or suspect attribution.
- Beacon may emit a signal referencing evidence IDs and reconciliation state.
- Luminary may explain a likely cause and propose options, labeled as inference.
- LIA may guide an authorized human and capture decision/approval evidence.
- Accounting alone records an authorized correction/reversal/reclassification.

None may mutate QBO evidence or treat a proposal as a posting. These downstream systems are not implemented by QBO.SOURCE.1.

## 10. Owner authorization gate

No owner action is required to validate this synthetic foundation. To connect the real company later, the owner must separately authorize a named operator/custodian and then:

1. Sign in at [Intuit Developer](https://developer.intuit.com/) and open **Dashboard → My apps**.
2. Select the dedicated ACP acquisition app (or authorize creation of one), enable **QuickBooks Online Accounting**, and verify legal/privacy/host/production requirements shown by Intuit.
3. Under **Keys & credentials**, keep Development and Production keys separate; place the exact approved HTTPS callback under **Redirect URIs**. Transfer the Production client secret directly into the approved secret manager—never chat, email, a ticket, a prompt, a shell command, docs, or Git.
4. From an owner-approved restricted acquisition workstation/service, start the ACP connection flow. On Intuit's consent screen, sign in, select the exact real company, confirm only QuickBooks Online Accounting access, and choose **Connect**.
5. Verify the returned `realmId` and `CompanyInfo` against owner-held company identity before authorizing extraction. Record owner approval, operator, custodian, app/environment, realm fingerprint, scope, and time without tokens.

**Stop gate:** QBO.SOURCE.1 stops before steps 2–5 are performed. A future milestone must implement and security-review the real adapter/evidence store first; owner consent alone does not authorize acquisition, rehearsal, ACP import, Preview, Production, or cutover.

## 11. Acceptance and next milestone

Acceptance requires focused tests proving digest integrity, mapping immutability, deterministic filtering, absence of write operations, preservation of an open source state, exact variance, and missing-not-zero behavior; full backend tests, lint/type checks, documentation links, clean secret scan, and Git gates must also pass.

The exact next milestone is **QBO.SOURCE.2 — Official Intuit Read-Only Adapter and Protected Evidence Store**, sandbox-first. It implements OAuth callback/state/PKCE where supported, secret-manager integration, realm binding, GET/query/report allow-list, pagination/rate/retry telemetry, immutable page store, snapshot sealing/drift detection, and sandbox contract tests. It still performs no real-company acquisition or ACP import; real connection remains a separate owner gate after security review.

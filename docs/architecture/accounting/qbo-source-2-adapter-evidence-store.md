<!-- markdownlint-disable MD013 -->

# QBO.SOURCE.2 — Official Intuit Read-Only Adapter and Protected Evidence Store

## Status and authority

QBO.SOURCE.2 implements the sandbox-first transport and custody boundary beneath [QBO.SOURCE.1](qbo-source-1-acquisition-foundation.md). QuickBooks Online remains authoritative only for what it reported. Native records, omissions, classifications, balances, statuses, relationships, and disagreements are preserved without correction. `SOURCE_REPORTED_STATE` is immutable; Enterprise Accounting alone may later post an authorized correction with separate evidence.

This milestone does not authenticate a real company, acquire real financial data, import into ACP, add database persistence or an Alembic revision, or touch Preview/Production.

## Official Intuit adapter architecture

`IntuitReadOnlyAdapter` implements `SourceAcquisitionProvider` as an asynchronous stream of `QboSourceEnvelope`. Its dependencies are deliberately external:

- `SecretProvider` resolves the Intuit client credential and rotating OAuth token from opaque secret-manager references. No environment value or secret is copied into a manifest, model, exception, log, fixture, or repository file.
- `IntuitOAuthClient` builds the authorization-code consent URL, exchanges a one-time code, refreshes rotating tokens, and revokes consent. It requests only `com.intuit.quickbooks.accounting`.
- `SerializedTokenManager` provides one refresh critical section per environment/realm, rechecks expiry after acquiring the lock, and performs generation-checked atomic token replacement.
- `IntuitHttpTransport` permits HTTPS only to official Intuit OAuth, revocation, sandbox, and production hosts. QBO company API hosts permit `GET` only. `POST` is restricted to OAuth token/revocation hosts, structurally preventing QBO creates, updates, deletes, voids, and report mutations.
- `RealmBinding` binds sandbox/production, exact `realmId`, owner-approved company name, and opaque credential/token references. Snapshot, adapter, OAuth client, and realm environment mismatches fail closed.

The two QBO bases are kept separate: `sandbox-quickbooks.api.intuit.com` and `quickbooks.api.intuit.com`. Production credentials cannot be used merely because Production endpoints exist in code; a Production `RealmBinding`, protected Production secret references, callback configuration, and separate owner authorization are all required.

Official sources: [Intuit OAuth 2.0](https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0), [authentication FAQ](https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/faq), [data queries](https://developer.intuit.com/app/developer/qbo/docs/learn/explore-the-quickbooks-online-api/data-queries), [minor versions and limits](https://developer.intuit.com/app/developer/qbo/docs/learn/rest-api-features), and [Accounting API entities](https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/account).

## OAuth and realm lifecycle

The application creates a high-entropy, expiring, single-use state bound to the initiating session and exact HTTPS callback. `build_authorization_url` includes the client ID obtained from the secret provider, exact redirect URI, authorization-code response type, accounting scope, and state. Callback handling must validate state before code exchange and bind the returned `realmId`; the actual HTTP callback route is intentionally deferred until an owner-approved acquisition host exists.

Code exchange and refresh use Basic client authentication only over the official token endpoint. A token response must contain both tokens, access expiry, and exactly the accounting scope. Refresh-token rotation is stored using compare-and-swap generation; concurrent callers receive the single refreshed access token. Authentication failures, invalid grants, revocation, company mismatch, or scope mismatch stop acquisition without fallback.

Revocation sends the current refresh token only to Intuit's revoke endpoint, then deletes protected token material only after Intuit accepts revocation. Non-secret audit evidence may retain realm fingerprint, app/environment identity, scope, generation, action, and time.

Every acquisition first calls `CompanyInfo/{realmId}` with the pinned minor version and compares the returned company name to the owner-approved binding. No other entity query is accepted before verification.

## Entity acquisition and fidelity

The adapter implements the QBO.SOURCE.1 entity catalog:

`CompanyInfo`, `Account`, `Customer`, `Vendor`, `Invoice`, `Payment`, `CreditMemo`, `Bill`, `BillPayment`, `VendorCredit`, `Purchase`, `CreditCardPayment`, `Deposit`, `Transfer`, `JournalEntry`, `TaxPayment`, `TaxAgency`, `Class`, `Department`, `Item`, `Employee`, `TimeActivity`, `RefundReceipt`, `SalesReceipt`, `Estimate`, and `PurchaseOrder`.

Requested applicability is explicit. If a QBO edition/locale does not support an entity or query, the run becomes a bounded partial failure; no empty or synthetic entity is invented. Purchases/expenses are native `Purchase`; receipts are `SalesReceipt` and `RefundReceipt`. Account types plus transaction/journal lines carry bank, cash, Undeposited Funds, liability, loan, fixed-asset, equity, retained-earnings, and AMEX evidence.

Queries use deterministic entity order from the request and `STARTPOSITION`/`MAXRESULTS` pages of at most 1,000. Each page records entity, ordinal, start position, count, raw digest, optional Intuit request ID, and content-addressed protected raw response. Repeated native IDs fail. A short page terminates enumeration.

Transient `408`, `429`, and `5xx` responses retry the identical GET at most four attempts. `Retry-After` is honored; otherwise exponential delay plus deterministic request-identity jitter is bounded at 30 seconds. `401/403`, other `4xx`, invalid JSON/schema, unsupported entity, realm mismatch, and exhausted retries fail without unbounded loops. No response bodies, authorization headers, tokens, or native payloads are logged.

## Protected evidence store

`ProtectedFilesystemEvidenceStore` is provider-neutral and must be configured with an owner-controlled root outside the Git repository. It rejects a repository-contained root and a pre-existing root with any group/other permission. Directories are `0700`; files are `0600`.

Raw canonical source JSON and raw page responses are stored once as SHA-256-addressed blobs. Envelope metadata is a separate immutable content-addressed document referencing the raw digest. Existing content must match byte-for-byte. A native entity key already recorded with a different raw digest is a hard conflict. Re-observing identical raw source during restart returns the original envelope reference, preserving the first acquisition timestamp and preventing duplication.

Run state is an atomic restricted checkpoint containing no raw payload. `begin_run` resumes an in-progress run only when snapshot and company binding match. Terminal sealing creates canonical compact UTF-8 JSON with stable key ordering and sorted entity/page rows. It records:

- run/schema identity and `in_progress`, `complete`, `partial`, or `failed` state;
- realm, environment, snapshot, August 25 cutoff/timezone, acquisition start/end, company name, and API minor version;
- per-entity counts and native identity/SyncToken plus raw/envelope digests;
- pagination evidence and raw page-blob digest;
- safe failure code for partial/failed runs.

An interrupted unsealed run is resumable without duplicate source objects. A caught provider failure seals a partial manifest; a later attempt uses a new run identity and reuses identical content-addressed blobs. Manifests do not contain financial rows. The store is protected, not a substitute for the approved host's encrypted volume/KMS, backups, retention/object-lock controls, and access audit.

## Immutable source envelope behavior

Nested native mappings/lists are recursively frozen. Construction verifies the canonical raw SHA-256. Persisted envelope metadata retains native type/ID, `SyncToken`, source create/update timestamps, relationship reference indexes, currency, reported status, lossless accounting-meaning indexes, snapshot/cutoff, acquisition timestamp, provider, and raw digest.

Indexes copy only values QBO supplied, including transaction date, amount/balance, payment type, account type/subtype, current balance, document number, and private memo. They do not infer payment application, job, material, vendor, account, posting date, or corrected status. Raw JSON remains controlling if an index is incomplete.

## August 25 control registration and reconciliation

`ControlEvidenceRegistry` registers only protected storage reference, raw file SHA-256, byte size, report kind, August 25, 2026 end date, Accrual basis, optional generation time, and safe report parameters. It accepts all eleven controls: Trial Balance, Balance Sheet, Profit & Loss, A/R Aging Detail, A/P Aging Detail, Account List, General Ledger, Customer Balance Detail, Open Invoices, Vendor Balance Detail, and Unpaid Bills. It never reads or commits their rows.

The QBO.SOURCE.1 `reconcile_amount` interface remains authoritative. Comparisons retain source IDs and control digest and return exactly `matched`, `exception`, `missing_source_evidence`, or `missing_control_evidence`. A missing amount produces no variance and is never converted to zero. Reconciliation cannot mutate an envelope or report registration.

## AMEX treatment

The adapter acquires AMEX account identity from native `Account` records and its QBO-classified activity from `Purchase`, `CreditCardPayment`, `Transfer`, `Deposit`, journal, credit/refund, and related supported records. Envelopes preserve native transaction date, any separately exposed source date, payee/vendor references, account/category references, `PaymentType`, memo/document reference, fee/interest line classification, currency, and all native reference links.

No issuer posting date is invented. No purchase is converted into AP. No account/category is reclassified. No job or material attribution is inferred. Missing issuer or economic attribution remains later reconciliation evidence.

## Configuration and real-company owner gate

No secrets are accepted through documentation, Git, a prompt, CLI arguments, URLs, logs, or fixtures. Deployment composition must provide only opaque references to an approved secret manager and an evidence root on an encrypted restricted volume. The callback URI must be an exact registered HTTPS URI, for example `https://<owner-approved-acquisition-host>/api/integrations/qbo/oauth/callback`; the final host is an owner/security decision and is not created here.

To connect the real company after QBO.SOURCE.2 review, the owner must:

1. Sign in to [Intuit Developer](https://developer.intuit.com/), open **Dashboard → My apps**, and select or authorize a dedicated ACP QBO acquisition app.
2. Enable **QuickBooks Online Accounting** and complete Intuit's Production app requirements. Development/sandbox keys remain separate.
3. Under the app's **Keys & credentials / Redirect URIs**, register the exact owner-approved HTTPS callback with an exact scheme, host, path, and port. No wildcard or unregistered redirect is accepted.
4. Place the Production client ID/secret directly into the approved Production secret-manager entries. Configure ACP with opaque references only. Place rotating tokens in a separate realm/environment-scoped secret entry. Configure the evidence root on the approved encrypted owner-only volume outside Git.
5. Start the ACP authorization flow from the restricted acquisition host. On Intuit's consent page, sign in, choose the exact real QBO company, verify the requested permission is QuickBooks Online Accounting, and select **Connect**.
6. ACP validates the one-time state, exchanges the code, captures returned `realmId`, and reads only CompanyInfo. The owner compares displayed CompanyInfo/company name and realm fingerprint to the intended company and separately approves the realm binding.
7. Stop before extraction. A separate owner acquisition authorization must name operator/custodian, snapshot/cutoff, entity plan, evidence root/retention, and control package. Consent and realm verification alone do not authorize acquisition or import.

## Validation and next milestone

Deterministic tests cover OAuth URL/code/refresh/revocation, serialized rotation, sandbox/production binding, CompanyInfo-first rejection, pagination, `Retry-After`, GET-only official transport, native envelope fidelity and nested immutability, restricted permissions, content addressing, deterministic sorting, restart deduplication, source-drift conflict, partial manifests, control metadata registration, and missing-not-zero reconciliation inherited from QBO.SOURCE.1.

The exact next milestone is **QBO.SOURCE.3 — Intuit Sandbox Connection Rehearsal and Control Reconciliation Workbench**. It adds the approved local callback/state store and secret-manager composition, connects only an Intuit sandbox company after owner sandbox authorization, executes/seals a sandbox acquisition, exercises every applicable entity/limitation, and generates reconciliation workpapers against synthetic or separately registered controls. It still does not connect the real company, import ACP data, or touch Preview/Production.

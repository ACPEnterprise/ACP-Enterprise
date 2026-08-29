<!-- markdownlint-disable MD013 -->

# QBO.SOURCE.3 — Sandbox Connection Rehearsal and Control Reconciliation Workbench

## Status and authority

QBO.SOURCE.3 completes every engineering preparation step available without external Intuit configuration. The inspected environment contained no approved sandbox client ID/secret, registered callback URI, token reference, or protected sandbox evidence root. Therefore no OAuth page was opened, no authorization code was requested, and no Intuit sandbox or real company was accessed.

This outcome is a configuration gate, not an application failure. The deterministic OAuth/acquisition tests remain synthetic and source-faithful. No data is imported into ACP, no migration is added, and Preview/Production remain untouched.

## Sandbox connection readiness

The exact unwired callback path is `/api/v1/integrations/qbo/oauth/callback`. The final callback is produced only from an owner-approved HTTPS origin and rejects wildcard, alternate path, query, fragment, or non-HTTPS input. `ProtectedAuthorizationStateStore` retains only hashed state filenames in a restricted `0700` directory with `0600` state files. Atomic claim/removal makes state single-use across processes. `OAuthCallbackHandler` rejects provider errors, incomplete callbacks, expired/replayed state, environment mismatch, and missing realm without logging callback values.

A live sandbox rehearsal still requires:

1. an Intuit Developer app with QuickBooks Online Accounting enabled and a sandbox company;
2. Development client credentials placed directly in an approved sandbox secret manager;
3. the exact callback URI registered in the Intuit app and configured identically in the restricted acquisition host;
4. opaque secret references for the client credential and sandbox realm token;
5. an owner-controlled encrypted evidence root outside Git and a separate restricted OAuth-state root;
6. an owner-authorized operator to initiate consent and choose only the intended sandbox company.

Once supplied, the rehearsal sequence is authorization request → protected single-use state → exact callback → code exchange → returned `realmId` → `CompanyInfo` name verification before queries → representative GET-only entity acquisition → forced serialized refresh/rotation proof → manifest sealing → revocation proof. Tokens, codes, state, authorization headers, and payloads must remain absent from logs and reports.

## Control reconciliation workbench

`EvidenceAssertion` preserves source namespace (`qbo`, `control_report`, `hcp`, or `amex_issuer`), evidence identity, subject, fact, and exact value. `ReconciliationWorkbench` compares two assertions without transforming either and returns only the existing classifications:

- `MATCHED`
- `EXCEPTION`
- `MISSING_SOURCE_EVIDENCE`
- `MISSING_CONTROL_EVIDENCE`

The finding holds both assertions and its winner is permanently `None`. Absence is represented by a missing assertion, never a numeric zero. A genuine QBO zero AP assertion can match a genuine control zero while a missing QBO AP assertion remains `MISSING_SOURCE_EVIDENCE`.

The registered August 25, 2026 Accrual reports remain protected metadata/checksum references: Trial Balance, Balance Sheet, Profit & Loss, A/R Aging Detail, A/P Aging Detail, Account List, General Ledger, Customer Balance Detail, Open Invoices, Vendor Balance Detail, and Unpaid Bills. The workbench does not load them from Git or rewrite them to force a tie.

## Source-faithful proving scenarios

Deterministic fixtures prove:

- QBO invoice status `open` versus HCP/independent status `paid` retains both assertions, returns `EXCEPTION`, selects no winner, and leaves the QBO assertion open.
- QBO AP `0` remains an actual zero when reported; missing source AP remains missing.
- a suspect AMEX QBO classification remains exactly the source classification; no replacement account is proposed by acquisition.
- HCP/QBO disagreement remains an explicit source conflict and cannot become a migration choice.

These scenarios are intentionally questionable accounting evidence. They are not fixture defects and are never cleansed.

## AMEX workbench

`AmexAccountEvidence` identifies the native QBO account/envelope, reported name/type/subtype, and currency. `AmexActivityEvidence` retains native type/ID/envelope, account, charge/credit/payment/fee/interest kind, amount, transaction date, separately reported posting/source date if present, payee/vendor, QBO classification, memo/reference, native links, any actual QBO job/customer/material attribution, and reconciliation state.

Missing job and material attribution are computed only as explicit missing flags. The contract does not infer them. Later Business Economics, Beacon, Luminary, and LIA consumers receive this evidence without posting authority.

## Drift and repeat acquisition

`SnapshotInventory` freezes a sealed manifest identity, run state, source observations, and ordered page digests. `compare_snapshots` retains both observations and reports:

- `CHANGED` for a digest/SyncToken change;
- `CHANGED_EARLIER_DATED` when the changed record's transaction date is on/before cutoff;
- `NEW` for a new identity;
- `DELETED` only when the second source mechanism explicitly supports deletion detection;
- `UNAVAILABLE` when an identity disappears without proof of deletion;
- `PAGINATION_CHANGED` for changed ordered page evidence; and
- `PARTIAL_COMPARISON` whenever either package is partial.

Snapshot A is a frozen mapping and is never updated with snapshot B. The protected evidence store already proves interruption resume, identical-object deduplication, changed-native-ID conflict, content reuse, and partial-run sealing. A later retry uses a new snapshot/run identity rather than pretending a partial observation was complete.

## ACC.MIG handoff

The exact non-executing handoff is:

`sealed source manifest + immutable envelope → versioned transformation plan → source-reported Enterprise representation → evidence-bound reconciliation findings → Finance disposition → separately authorized Accounting correction`.

`MigrationHandoff` requires both source manifest and envelope digests on the Enterprise source-reported record. A correction ID cannot exist without Finance disposition. Correction/reversal/reclassification evidence is additive; the original source assertion, raw digest, transformation version, and reconciliation lineage remain unchanged. This milestone neither invokes `OpeningStateTransformer` nor executes ACC.MIG.

## Intelligence proving contract

`IntelligenceProvingChain` requires exactly this deterministic order:

1. Business Economics identifies economic/data inconsistency.
2. Beacon raises an evidence-bound signal.
3. Luminary receives source/conflict evidence and explains likely cause/options.
4. LIA receives the recommendation/choices and guides an authorized resolution.
5. Accounting alone records an approved correction.

Every step must retain at least one source/conflict evidence identity from the first step. A non-Accounting step with posting authority fails contract construction. No model inference, prompt, recommendation engine, or speculative AI behavior is implemented.

## Real-company connection packet

The machine-readable packet is [QBO real-company connection packet](../../project/accounting-cutover/qbo-real-company-connection.packet.json). Owner-supplied values remain explicitly unresolved; no host, company, realm, credential, or storage path is guessed.

The owner must create/approve the dedicated Intuit Production app; complete Intuit's Production requirements; choose the acquisition host; register the exact URI `https://<OWNER_APPROVED_ACQUISITION_HOST>/api/v1/integrations/qbo/oauth/callback`; create the named secret-manager entries; provision the encrypted evidence/state roots; initiate consent; select the exact All County QBO company; approve only `com.intuit.quickbooks.accounting`; and independently compare returned realm/CompanyInfo before any extraction approval.

## Development credential provisioning

Legacy Development credentials are imported only through the repository-owned
sandbox command. The source files and target root must be protected paths outside
the repository. Credential values are never command arguments or command output.

```bash
cd backend
python -m app.qbo_source.credentials provision-development \
  --client-id-file /protected/qbo/sandbox/secrets/client-id \
  --client-secret-file /protected/qbo/sandbox/secrets/client-secret \
  --secret-root /protected/qbo/sandbox/secrets \
  --repository-root /app
```

The command accepts owner-held regular source files with restricted permissions,
writes `development-client.json` atomically with mode `0600` beneath a mode `0700`
directory, and is idempotent for the exact same pair. A conflicting existing
document, symlink, unsafe owner or permissions, malformed value, repository-local
source/target, or any Production provisioning request fails closed. Its JSON result
contains only status, sandbox environment, protected target path, and permission
metadata.

Revocation uses Intuit account **Sign-in & security → Apps with access to your account** or the adapter's official revoke flow. Abort on state/callback mismatch, wrong realm/company, wrong scope, secret-store failure, evidence-root failure, CompanyInfo mismatch, unexpected write method, partial acquisition, or unexplained drift. Abort preserves acquired immutable evidence and deletes no source record. Consent, realm verification, sandbox success, and Production credential availability do not authorize real extraction; that is a separate owner gate.

## Next milestone

The exact next milestone is **QBO.SOURCE.4 — Owner-Authorized Intuit Sandbox Live Rehearsal**. It begins only after the owner provides the approved sandbox app/callback/secret references/evidence roots. It performs the live sandbox sequence, seals sandbox evidence, validates applicable entity coverage and limitations, tests refresh/revocation, and produces a no-secret rehearsal record. It does not connect the real company, import ACP data, or touch Preview/Production.

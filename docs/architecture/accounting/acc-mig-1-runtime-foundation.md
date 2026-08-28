<!-- markdownlint-disable MD013 -->

# ACC.MIG.1 Native Opening-State Binding

## Status and authority

This foundation implements only the owner-authorized provider-neutral,
synthetic-input boundary beneath the accepted
[QuickBooks exit data contract](quickbooks-exit-data-contract.md),
[manifest schema](../../project/accounting-cutover/schemas/acc-mig-1-input-manifest.schema.json),
and [Accounting integration control](integration-control.md). It does not
authorize or implement a real QuickBooks adapter, real-data rehearsal, import,
Preview, Production, cutover, or any `TYPE C` operation.

The implementation starts from `ACC.DATA.1` commit
`e77897077baad0f6f79eec79cafb829cec36d4ca`. Its Python boundary is
`backend/app/accounting_migration/**`; focused tests are under
`backend/tests/accounting_migration/**`.

## Delivered boundary

`OpeningPackageValidator` consumes one immutable manifest plus package files.
It requires `synthetic: true`, the accepted contract/schema versions, all 34
primary artifact kinds, exact Company/Branch binding, a closed manifest shape,
unique artifact identities and safe relative paths, byte sizes and SHA-256
digests, exact row accounting, terminal artifact states, passed zero-variance
manifest controls, and preservation of the native-archive evidence identity.
Unknown kinds, properties, versions, layouts, paths, states, or real-input mode
fail closed with value-free reason codes.

`OpeningStateTransformer` is the provider-neutral source-to-plan seam. No
QuickBooks implementation is registered because actual headers, identities,
sign/date/open-balance/application semantics, and conditional applicability are
`SOURCE EVIDENCE REQUIRED`.

`OpeningStatePlan` defines target-independent opening journal lines, control
ties, row counts, rejection evidence, provenance, transformation identity, and
Company/Branch binding. It deliberately does not name tables, ORM models, or
target identifiers that are not yet authoritative.

`OpeningMigrationRuntime` validates balanced debits/credits, exact control ties,
complete manifest-to-plan row accounting, explainable rejects, provenance,
finite exact decimal amounts, and package/Company/Branch/version identity. It
creates deterministic plan, idempotency, and audit digests. An identical replay
returns zero delta; a changed plan under the same package identity fails as a
contradictory replay.

`RehearsalTarget` is the target-side transaction seam. The only included target
is `RollbackOnlyTarget`, which can stage synthetic journal lines but has no
commit operation and proves zero committed records after every run. The
in-memory append-only checkpoint implementation proves retry/resume semantics
without claiming durable Production evidence.

`NativeOpeningStateService` is the accepted provider-neutral handoff into native
Accounting. It maps source account and Branch identities to approved native
targets, verifies the active chart, accounting basis, currency, period,
balance-sheet classification and applicable control-account assignments, and
produces a deterministic reconciliation package. Each line preserves source
authority, source and imported-value digests, target identity, expected and
prepared debit/credit, difference, limitations, reconciliation identity and
state. Missing or contradictory evidence is represented as unknown rather than
zero and is never eligible for posting.

Posting uses `AccountingService.create_journal`, `prepare_journal`,
`approve_journal`, and `post_journal`; it never writes balances directly. The
opening journal carries the canonical reconciliation digest as its posting
source, a deterministic package/version idempotency key, Finance approval
evidence, and the native control-override evidence. Existing Accounting
separation of duties, immutable audit entries, Business Events, posting-source
deduplication and contradictory-replay checks therefore govern the opening
state. A lifecycle failure is also sent to the existing durable Accounting
posting-failure evidence seam.

The posted opening journal is an ordinary immutable native ledger fact. ACC.RPT.1
continues to read only posted General Ledger activity, so trial balance,
balance-sheet and report checksum/cutoff behavior require no external-record
exception.

## Explicit blockers

### Persistence decision

No new table or Alembic revision is required. Successful authority is already
durable in the native journal, journal lines, posting-source identity, approval,
audit and Business Event records. Failed posting evidence uses the existing
Accounting posting-failure store. Pre-post reconciliation remains a canonical,
digest-bound value contract and cannot be confused with posted ledger truth.

## Finance prerequisites deliberately unresolved

The service requires explicit versioned references for opening-balance
acceptance, reconciliation precedence, retained-earnings treatment,
opening-equity treatment, unresolved AR/AP treatment, unresolved bank/cash
treatment, materiality, cutover date, period and currency. It validates these
inputs but supplies no default policy. Account mapping also requires a Finance
mapping reference. Provider acquisition and the 298 HCP/QBO balance assertions
remain outside this boundary.

### Source evidence

A real-field adapter remains blocked until authoritative evidence supplies the
QuickBooks edition/version, stable company/account/party/transaction identities,
actual exports and report definitions, sign/date/open-balance/application
semantics, COA/control mappings, Company/Branch allocation, currency/locale,
accounting basis, period/cutoff convention, conditional-artifact applicability,
and secure non-Git rehearsal-data handling. Unknown semantics remain
`SOURCE EVIDENCE REQUIRED`; they are never inferred from synthetic fixtures.

## Real-export rehearsal entry conditions

Real-export rehearsal can be proposed only after all of the following exist:

1. all predecessor runtime schemas and public adapters are accepted and
   integrated in order with exactly one Alembic head;
2. an accepted, versioned source adapter built from the source evidence above;
3. an immutable complete real-export package whose raw-byte checksums, controls,
   Company/Branch binding, row counts, archive linkage, and dispositions pass;
4. durable restricted-data audit/checkpoint/rejection evidence and an approved
   security/access/retention boundary outside Git;
5. a disposable or transactionally isolated rehearsal target, backup and
   rollback proof, and deterministic zero-variance repeatability;
6. separate owner authorization for the `TYPE C` rehearsal and independent
   Finance review; and
7. any separately required Preview authorization. Production and cutover remain
   additional owner gates.

## Deadline risk

The August 21, 2026 objective is at risk until target schemas, source evidence,
restricted rehearsal handling, and Finance availability are supplied. The
synthetic foundation removes loader-mechanics uncertainty but cannot compress
the serialized Accounting integrations or waive a missing export, unexplained
variance, security control, Finance approval, Preview gate, or Production gate.

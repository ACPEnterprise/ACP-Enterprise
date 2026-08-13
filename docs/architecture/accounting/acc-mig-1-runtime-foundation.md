<!-- markdownlint-disable MD013 -->

# ACC.MIG.1 Synthetic Runtime Foundation

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

## Explicit blockers

### Target schemas

No Accounting persistence, ORM mapping, API, target adapter, or Alembic revision
is created. Those remain blocked until the authoritative sequence lands:

`ACC.CORE.1 → INVOICE.1-3.ACCEL → PAY.1-3.ACCEL → ACC.AP.1 → ACC.POST.1 → ACC.RPT.1 → ACC.MIG.1`.

After those contracts exist, ACC.MIG.1 must bind its plan classes to their
public interfaces without directly writing another domain's tables. If durable
run/audit/rejection persistence is still required, its migration owns slot 7,
must descend from the then-current single authoritative head, and must pass the
full serialization protocol. No sibling head is permitted.

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

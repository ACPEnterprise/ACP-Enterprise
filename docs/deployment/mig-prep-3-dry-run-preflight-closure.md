# MIG.PREP.3 — Representative dry-run execution contract and preflight closure

MIG.PREP.3 closes the non-operational architecture around the MIG.PREP.2
contracts. It adds one deterministic, read-only assessment that binds an approved
manifest, observed artifact checksums, mapping conformance, tenant scope,
environment evidence, identity summaries, owner dispositions, teardown,
resume/retry, audit requirements, and external approvals. It has no repository,
database, import, synchronization, provider, deployment, or cutover port.

## Exact future execution identity

A future run is identified by its approved manifest UUID/digest, exact executing
Git SHA, Company, Branch, isolated environment identity, and run UUID. Each
artifact must match the manifest's content SHA-256 and byte size. Artifact IDs and
the ten-entity boundary must match exactly. The preflight never supplies a missing
dataset identity or checksum: absence is `input:immutable_manifest_missing`.

`launch-migration-mapping/v1` remains authoritative. Customer, Contact, Service
Location, Job, Appointment, Invoice, and Payment are included. Estimate, Note,
and Attachment remain owner-excluded. Transformation versions and unsupported
CRM.2 optional-field behavior remain governed by MIG.1/MIG.PREP.2.

## Identity, disposition, and exception closure

Each included entity reports input, valid, missing, duplicate, ambiguous,
conflicting, unresolved-target, and owner-disposition-required counts. Every input
must reconcile exactly to the mutually classified identity outcomes. Required
owner dispositions must reconcile to resolved plus unresolved, and every resolved
decision requires one canonical immutable digest. Any unresolved disposition
blocks execution.

The MIG.PREP.2 exception taxonomy remains unchanged. Duplicate identities are
classified evidence, never merged. Ambiguous, conflicting, unresolved, or
cross-tenant evidence fails closed. Infrastructure and environment failures remain
distinct from source-data exceptions.

## Rollback-only environment and retry

The environment contract accepts only synthetic or sanitized non-production
classification. It requires Company/Branch scope, hashed database/configuration
identity, network isolation, no Preview access, no Production access, and no
operational persistence after teardown.

Retries require the same manifest and code SHA. The ordered checkpoints are input,
mapping, identity, transformation, parent resolution, import transaction,
reconciliation, and teardown. Resume uses run identity plus the last verified
checkpoint. Replay must prove zero delta. Teardown remains run-, Company-, and
Branch-bounded and retains immutable manifest, reconciliation, exception, timing,
approval, audit, and teardown evidence.

## Audit and readiness

The append-only audit contract requires ordered preflight-started, dependencies,
environment, input, mapping, identity, teardown, and preflight-sealed events. The
assessment canonically seals completed gates and blockers with SHA-256 and UUIDv5.

Technical executability means every architecture/evidence check passes. Execution
authorization additionally requires immutable evidence for all external gates:

- MIG.1 complete;
- IC.2 complete and accepted;
- RPT.3 complete and accepted;
- the specific immutable non-production input approved;
- separate TYPE C MIG.2 operation approval.

MIG.PREP.3 does not satisfy or infer these external gates. Based on evidence
available when this package was authored, only MIG.1 is complete. MIG.2 therefore
remains blocked by IC.2, RPT.3, the actual approved immutable dataset/environment,
and explicit TYPE C authorization. No manifest checksum can truthfully be reported
until that dataset is supplied and approved.

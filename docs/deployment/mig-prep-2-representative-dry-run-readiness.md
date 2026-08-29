# MIG.PREP.2 — Representative dry-run readiness package

MIG.PREP.2 is readiness engineering only. It does not make `MIG.2` ready and
does not authorize an import, synchronization, provider interaction, Preview or
Production access, teardown, or cutover. `MIG.2` remains a separately approved
TYPE C operation.

## Immutable input manifest

The future approved non-production dataset must be sealed by
`representative-dry-run-readiness/v1`. Its canonical manifest records dataset and
provider identity; sorted transformation versions; per-entity counts; hashed
filename and content identities; artifact sizes; timezone-aware creation time;
source provenance; Company and Branch; the seven included and three owner-excluded
MIG.1 entity classes; synthetic or sanitized-non-production classification;
sanitization evidence; owner approval identity and evidence; mapping version; and
the exact executing Git SHA. Canonical SHA-256 produces the manifest digest and a
UUIDv5 manifest identity.

Raw provider data is neither needed nor permitted to prepare this contract.

## Mapping-conformance preflight

The preflight requires `launch-migration-mapping/v1`, all registered
transformation versions, and field evidence for Customer, Contact, Service
Location, Job, Appointment, Invoice, and Payment. Estimate, Note, and Attachment
remain excluded by owner. A populated CRM.2 optional field that MIG.1 deliberately
left unknown fails closed; it is never inferred or defaulted. Missing required
fields, missing transformation versions, duplicate evidence, unknown entities, or
data for excluded entities also fail closed.

LOCATION.2 native-ID-first matching, SOURCE.5 Customer consolidation, Company and
Branch scope, owner dispositions, exact Decimal values, immutable evidence, and
deterministic replay remain authoritative.

## Future MIG.2 execution plan

When every separate gate is approved, the operator follows this fixed order:

1. dependency verification;
2. environment verification;
3. immutable-input verification;
4. mapping-contract verification;
5. identity validation;
6. transformation;
7. parent resolution;
8. representative non-production import boundary;
9. reconciliation;
10. exception classification;
11. timing and throughput measurement;
12. result sealing;
13. teardown;
14. owner review.

Only step 8 is an import. Nothing in MIG.PREP.2 executes any step.

## Exception ledger and reconciliation

Data/mapping exceptions are: missing or duplicate source identity, ambiguous
identity, unresolved Enterprise target, missing or conflicting parent,
transformation rejection, unsupported lifecycle, owner disposition required,
Company or Branch mismatch, monetary or evidence mismatch, unsupported optional
field, excluded V1 entity, and replay conflict.

Application/environment failures are: application invariant, database,
transaction, infrastructure, unavailable dependency, environment/configuration,
interruption, and teardown failures. They must never be relabeled as source-data
exceptions.

Each entity must satisfy both equations:

`input = included + excluded`

`included = accepted + rejected + unresolved`

Parent resolved plus parent unresolved must equal included. Duplicate, ambiguity,
and owner-disposition categories cannot exceed unresolved. Monetary input must
equal accepted plus rejected plus excluded plus unresolved exactly, with no
rounding or inferred allocation. The sealed report records evidence, exception,
and result digests plus retry/replay and teardown results. No unexplained drop is
valid.

## Timing and repeatability

Future measurement captures total, per-entity, identity resolution,
transformation, persistence, reconciliation, teardown, and replay durations in
monotonic nanoseconds, plus processed records and derived records per second. No
performance SLA is established here.

MIG.3 comparison evidence preserves manifest, mapping and transformation versions,
code SHA, environment identity, entity-count, reconciliation, exception, result,
timing, and teardown digests. Its deterministic comparison digest excludes wall
clock timing so equivalent results remain comparable while timing evidence stays
auditable.

## Teardown and recovery contract

Every future created aggregate must carry the representative run identity and
Company/Branch scope. Teardown runs child-first in an explicitly numbered order;
every selector must include the run identity. It fails closed if a selector could
reach outside that boundary. An interruption resumes from run identity plus the
last verified step. Completion requires zero run-owned operational rows and clean
foreign keys. Manifest, reconciliation, exception, timing, approval, and teardown
evidence remain immutable; operational test aggregates do not.

A teardown failure is an application/environment failure, leaves the environment
blocked, records the exact last completed step, and requires owner review before
any retry.

## MIG.2 operator runbook

### Pre-run

- Verify MIG.1 is complete and the exact Migration SHA is approved.
- Verify IC.2 and RPT.3 are complete and owner accepted.
- Verify any required Enterprise/integration SHA and exactly one Migration
  Alembic head.
- Verify the immutable dataset approval, manifest digest, artifact checksums,
  non-production classification, Company/Branch scope, and executing code SHA.
- Verify the isolated non-production environment and that no Preview or Production
  endpoint is configured.
- Verify bounded teardown/rollback capability and explicit owner TYPE C operation
  approval.

### Run

- Execute preflight and stop on every violation.
- Execute the representative import only inside its approved environment and run
  boundary.
- Capture monotonic timing and the typed exception ledger.
- Reconcile entity counts, parents, and exact monetary values.
- Replay as authorized, then seal reconciliation, timing, repeatability, and
  teardown evidence.

### Post-run

- Inspect every reconciliation equation and unresolved exception.
- Verify replay and repeatability evidence.
- Execute bounded child-first teardown; verify zero run-owned rows and foreign-key
  integrity.
- Preserve required immutable evidence and stop for owner review.

### Immediate stop conditions

Stop for missing/unaccepted MIG.1, IC.2, or RPT.3; missing operation approval;
unapproved, mutable, live, or checksum-mismatched input; wrong code or contract
version; wrong Company/Branch; unknown or excluded entity data; unsupported
optional values; identity ambiguity or conflict; missing parent; unexplained count
or monetary variance; replay conflict; unavailable teardown; selector escaping the
run boundary; application, database, transaction, infrastructure, configuration,
or dependency failure; interruption; evidence-sealing failure; Preview/Production
configuration; or any request to broaden scope or infer evidence.

## Readiness gates remaining after MIG.PREP.2

MIG.2 remains blocked until IC.2 and RPT.3 are complete and owner accepted, a
specific immutable non-production input manifest is approved, and the owner grants
separate TYPE C operation approval. Completing this package satisfies none of
those external gates.

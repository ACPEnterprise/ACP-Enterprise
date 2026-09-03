# Real-data operational acceptance harness

`OPERATIONS.REALDATA.ACCEPTANCE.v1` answers one bounded launch question: did an
admitted HCP operational record preserve its identity, relationships, scope, and
Schedule/Dispatch projections in ACP?

The harness is post-admission and read-only. Migration supplies a projection
bundle from its accepted SOURCE.4/native reconciliation boundary. The harness
does not read acquisition artifacts, import records, select mappings, repair
lineage, or mutate any ACP domain.

## Verified chain

For each bounded Company/Branch/date selection, the bundle contains:

1. digest-bound Customer identity lineage;
2. Service Location identity and Customer parent;
3. Job identity and Customer/Location parents;
4. Appointment identity and Customer/Location/Job parents;
5. admitted SOURCE.4 appointment status, arrival window, and technician IDs;
6. the native Scheduling projection;
7. the native Dispatch projection;
8. explicit source-technician crosswalk evidence.

The harness composes the accepted `hcp-acp-schedule-comparison.v1` contract. It
does not define another Scheduling comparison or lifecycle mapping.

## Results

- `MATCHED`: identity, relationship, scope, and projections agree.
- `PARTIAL`: admitted evidence remains incomplete, such as an explicitly
  unmapped technician. Nothing is fabricated.
- `MISSING_NATIVE`: an admitted source identity or product projection lacks a
  native counterpart.
- `ORPHANED`: required source/native parent lineage is absent.
- `CONFLICTING`: duplicate identity, scope, relationship, status, arrival
  window, or technician evidence disagrees.

Every finding binds the source digest, bounded native digest, stage, domain,
identity, and conditions. Canonical ordering makes unchanged input produce the
same report digest. Conflicting, missing-native, or orphaned output returns a
non-zero command status; partial output remains reviewable without pretending
it is complete.

## Execution

Enterprise exports only the admitted projection bundle—never raw sealed HCP
payloads—and runs:

```text
python -m scripts.operational_realdata_acceptance \
  --input /protected/operator-selected/admitted-projections.json \
  --output /protected/operator-selected/acceptance-report.json
```

The input has top-level `company_id`, optional `branch_id`, and bounded arrays
named `lineage`, `appointments`, `schedules`, `dispatches`, and `crosswalks`.
Each array is capped at 10,000 records. Company and Branch ownership comes from
server-generated projections, not operator-entered labels.

The report separates `LINEAGE` failures (acquisition, mapping, identity, native
persistence) from `OPERATIONAL_PROJECTION` failures (Scheduling and Dispatch),
allowing Enterprise to route a defect to the owning boundary without changing
source truth.

## Preview gate

Real execution remains gated on
`MIGRATION.HCP.PREVIEW.SUCCESSOR.RECONCILIATION.1` admitting SOURCE.4 data and
providing the bounded server-generated projection bundle. No additional
architecture or import path is needed after that gate opens.

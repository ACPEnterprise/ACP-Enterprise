# Assets/Fleet operationalization program 3

## Source inventory contracts

Customer equipment requires source identity, Company/Branch, authoritative Customer and Service Location IDs, source/provenance, equipment class, status, and any explicitly sourced manufacturer, model, serial, installation, replacement, Job-service, warranty, or document evidence. Vehicles require source identity, Company/Branch, asset number or protected VIN evidence, status, and any explicitly sourced plate, make/model/year, assignment, operational location, registration, inspection, or maintenance evidence. Tracked tools/equipment require source identity, asset number, class, Branch, status, and explicit custody/document evidence. Optional values remain absent; free text never becomes identity authority.

## Reconciliation and import

Synthetic import preview produces `EXACT_IDENTITY`, `STRONG_CANDIDATE`, `AMBIGUOUS`, `INSUFFICIENT_EVIDENCE`, `CONFLICT`, `NEW_ASSET_CANDIDATE`, or `REPLACEMENT_CANDIDATE`. Source-system identity plus digest governs replay. Changed content under the same source identity conflicts; no Asset is created by preview. Weak similarity can only create a review candidate. Missing/foreign Customer, Location, Branch, Employee, Job, custody, and document evidence remains blocked.

Before acceptance, preview rows may be rejected through a future reviewed disposition. Once operational evidence is accepted, rollback means append-only correction/supersession—not deletion. Interrupted import resumes by source identity and idempotency key.

## Versioned policy readiness

Inspection, maintenance, out-of-service, warranty, sensitive-identifier, and import policies support immutable draft versions, predecessor lineage, effective dates, canonical digests, and explicit `UNCONFIGURED` state. This program does not activate real policy. Preview impact must report affected Assets and missing evidence without manufacturing due dates.

Owner decisions still required:

- inspection definitions, applicability, cadence, required items, and readiness consequences;
- maintenance triggers/intervals, evidence requirements, and return-to-service authority;
- out-of-service consequences;
- warranty evidence, eligibility/review, callback, and Customer-display policy;
- VIN/serial/plate view, search, masking, LIA, Mobile, event, and log treatment;
- import source ownership and final acceptance authority.

## Readiness and data quality

The owner workspace projects `ENGINEERING_READY`, `DATA_REQUIRED`, `POLICY_REQUIRED`, `REVIEW_REQUIRED`, `CONFLICTING`, and `EXTERNAL_GATE`. It reports import classifications and each policy family independently. Missing information is readiness evidence, not a fabricated business fact.

## Cross-domain boundaries

Customer 360, Jobs, Workforce, Inventory, Purchasing, Accounting, Economics, Beacon, LIA, and Mobile consume bounded references only. Operational Assets do not mutate those domains, expose Payroll/banking data, move stock, post journals, calculate depreciation/value/profitability, generate Beacon signals, permit LIA mutation, or deploy Mobile.

## Cutover checklist

1. inventory source files and owners;
2. validate fields/provenance and protected documents;
3. dry-run classifications and duplicate review;
4. resolve Customer/Location/Branch/Employee conflicts;
5. approve policy versions separately;
6. establish opening assignments/custody without guessing;
7. run synthetic and Preview acceptance;
8. reconcile a final delta by source identity;
9. owner go/no-go;
10. preserve immutable accepted history and recovery evidence.

## Operational readiness matrix

| Area | State before real configuration/data |
|---|---|
| Asset identity, Customer equipment, warranty/service/Fleet/inspection/maintenance/custody evidence | ENGINEERING_READY |
| Equipment/vehicle/tool import and reconciliation | DATA_REQUIRED |
| Inspection, maintenance, warranty, out-of-service, identifier policies | POLICY_REQUIRED |
| Duplicate/conflict/import dispositions | REVIEW_REQUIRED |
| Protected document provider and Preview deployment | EXTERNAL_GATE |
| Customer 360, Job, Workforce, Inventory, Purchasing composition | ENGINEERING_READY |
| Mobile, LIA, Beacon, Economics consumers | DEPENDENCY_BLOCKED |
| Cutover | DATA_REQUIRED |

No real data, policy activation, cutover, Preview deployment, or Production operation is authorized by this packet.

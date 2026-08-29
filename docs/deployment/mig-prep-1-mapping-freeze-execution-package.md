# MIG.PREP.1 — MIG.1 mapping-freeze execution package

Status: prepared; MIG.1 remains `PLANNED` and blocked on owner-accepted OPS.1.

This package is non-executable and contains no source rows, customer data,
credentials, runtime manifests, approvals, or inferred mappings. It preserves the
accepted Customer Migration architecture through LOCATION.2, SOURCE.5, CUTOVER.1,
and CUTOVER.2. It neither changes historical evidence nor authorizes import,
synchronization, cutover, integration, deployment, or operational-entity mutation.

## MIG.1 starting contract

| Control | Required contract |
| --- | --- |
| Repository | `ACP-Enterprise`, Customer Migration workstream only. Do not edit the authoritative Enterprise/OPS worktree. |
| Branch | `customer-migration-workstream`. Use a dedicated clean worktree for MIG.1 if another task is active. |
| Starting SHA | Fetch origin immediately before start. The start SHA is the then-current `origin/customer-migration-workstream`, must be a descendant of `b66955f3df5b0daf62ee57d488d5f49e53338942`, and must equal local HEAD. Stop on divergence or unrelated local changes. Never substitute a remembered SHA. |
| OPS.1 dependency | Require owner-accepted OPS.1 completion evidence described below. An `IN PROGRESS`, technically complete, or unapproved state is insufficient. |
| Migration impact | Mapping freeze may version provider-neutral mapping/reconciliation contracts and tests only. Existing evidence stays immutable. Any Alembic or operational-schema requirement is outside this start contract and requires a stop. |
| Integration checkpoint | Compare the owner-accepted OPS.1 contract packet with the inventory below before changing mappings. Record compatible, changed, missing, and semantically conflicting fields/statuses/relationships. No history merge is implied. |
| Environment boundary | Synthetic/no-live-data validation only. No provider call, source extraction, import, synchronization, Preview/Production access, deployment, or infrastructure action. |
| Owner checkpoints | (1) OPS.1 owner acceptance; (2) mapping-delta review for any semantic change; (3) reject/disposition coverage review; (4) immutable mapping-freeze review. None may be inferred from tests. |
| Validation boundary | Contract consistency, traceability, complete entity inventory, dependency closure, taxonomy/disposition coverage, deterministic reconciliation, replay, tenant isolation, synthetic fixtures, static checks, and unchanged single Alembic head. |
| Stop conditions | OPS.1 ambiguity; missing authoritative identity/relationship; new business rule; semantic conflict; schema migration; immutable-evidence change; live data/environment access; import/cutover behavior; or scope beyond mapping freeze. |
| Commit boundary | Versioned mapping contracts/registry, synthetic tests, and non-sensitive documentation created for MIG.1 only. Exclude raw exports, runtime evidence/manifests, backups, credentials, tokens, PII, generated output, imports, and unrelated refactors. |

### Required OPS.1 completion evidence

The future start packet must identify, without inference:

- OPS.1 milestone status `OWNER ACCEPTED / COMPLETE`, owner-review evidence identity,
  completion timestamp, authoritative repository, branch, and commit SHA;
- the exact changed-file list and API/domain contract versions delivered by OPS.1;
- target identities, required/optional fields, lifecycle/status values, Company and
  Branch ownership, foreign keys, uniqueness, and optimistic-concurrency behavior
  for every OPS.1-owned launch entity or relationship;
- Alembic revision/head and an explicit statement of integration impact on this
  isolated Migration lineage;
- synthetic validation evidence and unresolved owner/product decisions;
- a compatibility statement for Job, Appointment, Estimate, Invoice, Payment,
  Note, and Attachment mappings, including scheduling/dispatch relationships.

If OPS.1 cannot supply an authoritative value, MIG.1 records that item as a blocker;
it does not fill the gap from names, addresses, job numbers, timestamps, or defaults.

## Launch-entity mapping inventory

“Required” and “optional” below describe the currently approved migration input
contracts. They do not assert that OPS.1 will preserve those contracts.

### Customer

- **Source identity:** provider-scoped `source_customer_id`; SOURCE.5 additionally
  uses the provider/entity-scoped SHA-256 identity under
  `native-customer-identity-consolidation/v1`.
- **Target identity:** `CustomerSourceIdentity` → Enterprise `Customer.id`, scoped
  by Company and Branch.
- **Contracts:** registered Housecall Pro layouts
  `housecall_pro_customer_444_v1`, `housecall_pro_customer_451_v1`, and
  `housecall_pro_customer_450_v1`; reviewed output
  `customer-adapter-review/v1`; immutable boundary
  `customer-pilot-boundary/v1`; SOURCE.5 consolidation v1.
- **Required fields:** safe source ID, customer type, display name. The adapter may
  derive display name/type only by its already-approved explicit rules.
- **Optional fields:** legal name, contact preference, marketing source, tax-exempt
  state, notes, status, and supported child records.
- **Reject/duplicate:** `source_checksum_mismatch`, `unsupported_encoding`,
  `unsupported_customer_export_schema`, `missing_required_field`,
  `unsupported_customer_type`, `unsupported_billing_flag`,
  `multiple_billing_addresses`, `contact_name_unresolved`,
  `customer_name_unresolved`, `incomplete_address_group`,
  `domain_validation_failed`, `duplicate_source_identity`, oversized identity,
  and SOURCE.5
  outcomes `missing_source_identifier`, `duplicate_source_evidence`,
  `conflicting_source_evidence`, `ambiguous_target`, `existing_binding_conflict`,
  `company_branch_scope_conflict`, and
  `multiple_native_identities_one_customer`.
- **Disposition/evidence:** approved `owner-disposition/v1` decisions; reviewed-output,
  manifest, source/transformation/review digests; append-only consolidation evidence.
- **Open dependency:** OPS.1 must confirm whether any Customer ownership, lifecycle,
  required field, or operational relationship changed. No mapping change is assumed.

### Contact

- **Source identity:** `CustomerContactSourceIdentity.source_contact_id` linked to
  the authoritative Customer source identity. Where the export supplies only the
  accepted aggregate contact, its existing child-identity convention is preserved;
  no new contact identity may be invented.
- **Target identity:** Enterprise `CustomerContact.id` under `Customer.id`.
- **Contract:** Customer adapter/review contracts above and strict `ContactCreate`.
- **Required fields:** first and last name for a created Contact, authoritative
  parent Customer.
- **Optional fields:** title, email, mobile/office phone, preferred/active flags,
  notes; the entire Contact is optional on the Customer aggregate.
- **Reject/duplicate:** unresolved/missing names, multiple-email resolution,
  invalid email/phone, inactive preferred contact, duplicate source or target.
- **Disposition/evidence:** `contact_name_resolution`, source-correction or explicit
  owner decision; child exception and source identity evidence.
- **Open dependency:** confirm OPS.1 did not change Contact ownership or validation.

### Service Location

- **Source identity:** provider/entity-scoped native Service Location SHA-256 under
  `native-service-location-identity/v1`; raw provider identity remains distinct
  from Enterprise identity. Legacy derived location IDs are historical evidence,
  not proof of a native identity.
- **Target identity:** `ServiceLocationSourceIdentity` → Enterprise
  `ServiceLocation.id`, bound to the same authoritative Customer and Company;
  Branch scope is preserved by LOCATION.2 evidence.
- **Contracts:** native identity v1, `native-service-location-matching/v1`,
  `customer-location-evidence/v1`; strict `ServiceLocationCreate`.
- **Required fields:** native ID for automatic identity matching, source Customer
  binding, complete address (address, city, state, postal code), Company/Branch.
- **Optional fields:** nickname, address line 2, country default, coordinates,
  billing override, gate code, property notes, active state.
- **Reject/duplicate:** every LOCATION.2 classification, including missing or
  duplicate native ID, one ID/multiple locations, one address/multiple IDs,
  parent mismatch/missing parent, incomplete address, scope conflict, existing or
  prior binding conflict, ambiguous address, address-review-required, and generic
  reconciliation-required.
- **Disposition/evidence:** address exception and explicit owner review; append-only
  identity/reconciliation evidence. Address equality never merges identities.
- **Open dependency:** OPS.1 must confirm target ownership/relationship constraints.

### Job

- **Source identity:** stable provider Job ID only; Job number alone is prohibited.
- **Target identity:** `JobSourceIdentity` → Enterprise `Job.id`, with exact
  Customer and Service Location source identities.
- **Contracts:** `operational-phase1-hcp/v1`, review/manifest v1, selection
  `source-identity-sha256/v1`; provider-neutral `JobMigrationRecord`.
- **Required fields:** source ID, source Customer ID, source Service Location ID,
  status; accepted Customer/Location parents.
- **Optional fields:** job number, lifecycle timestamps, summary, description,
  priority, technician IDs, metadata.
- **Reject/duplicate:** `missing_job_source_identity`,
  `duplicate_job_source_identity`, `service_location_not_migrated`,
  `customer_identity_unresolved`, `customer_signals_conflict`,
  `customer_identity_ambiguous`, duplicate normalized migration identity,
  existing source identity/job number, invalid priority/status, or record validation.
- **Disposition/evidence:** accepted/rejected/duplicate/unresolved outcomes, phase-1
  review/manifest/replay evidence and explicit owner disposition for unresolved
  parents or identities.
- **Open dependency:** historical Job source completeness remains separate; OPS.1
  must freeze Job lifecycle, ownership, and dispatch-related target contracts.

### Appointment

- **Source identity:** stable provider Appointment ID linked to stable Job ID.
- **Target identity:** `AppointmentSourceIdentity` → Enterprise `Appointment.id`,
  with Job, Customer, and Service Location bindings.
- **Contracts:** phase-1 contracts and provider-neutral
  `AppointmentMigrationRecord`.
- **Required fields:** source/Job/Customer/Location IDs, status; arrival fields are
  contract members but may be null.
- **Optional fields:** arrival window, duration, technician IDs, notes, metadata.
- **Reject/duplicate:** missing/duplicate identity, duplicate parent/window,
  missing Job, parent mismatch, invalid status/window/duration, wrong tenant scope.
- **Disposition/evidence:** phase-1 outcomes and reconciliation/replay evidence.
- **Open dependency:** OPS.1 must freeze scheduling/dispatch status and relationship
  semantics before MIG.1 can freeze this mapping.

### Estimate

- **Source identity:** stable provider Estimate ID linked to Job source identity.
- **Target identity:** `EstimateSourceIdentity` → Enterprise `Estimate.id`; line
  items use `EstimateLineItemSourceIdentity`.
- **Contract:** provider-neutral `EstimateMigrationRecord` and
  `FinancialLineItemRecord`. The accepted 2024 phase-2 transformation exported no
  Estimates; therefore no provider-specific Estimate mapping is frozen yet.
- **Required fields:** source and Job IDs, status, currency, exact subtotal/tax/total,
  and line items with source ID, description, quantity, unit price, total.
- **Optional fields:** presented timestamp, expiration date, metadata.
- **Reject/duplicate:** missing parent, duplicate/existing identity, validation
  failure, unsupported lifecycle, incomplete detail, monetary imbalance.
- **Disposition/evidence:** financial accepted/rejected/duplicate/unresolved outcome,
  exact-value reconciliation; provider mapping requires owner-approved evidence.
- **Open dependency:** OPS.1 target contract plus a separately authoritative source
  transformation are required. MIG.1 must not manufacture either.

### Invoice

- **Source identity:** stable provider Invoice ID linked to Job source identity.
- **Target identity:** `InvoiceSourceIdentity` → Enterprise `Invoice.id`; line items
  use `InvoiceLineItemSourceIdentity`.
- **Contracts:** `operational-phase2-hcp-financial/v1`, phase-2 review/manifest v1,
  selection `source-identity-sha256/v1`, provider-neutral Invoice record.
- **Required fields:** source/Job IDs, status, currency, exact subtotal/tax/total,
  and complete line-item monetary fields.
- **Optional fields:** issued timestamp, due date, metadata.
- **Reject/duplicate:** `unresolved_job`, `unresolved_invoice`,
  `duplicate_source_identity`, `monetary_imbalance`, parse/incomplete-detail errors,
  missing parent, existing identity, validation failure, unsupported lifecycle.
- **Disposition/evidence:** immutable phase-2 review/manifest and exact financial
  reconciliation; no inferred totals, taxes, balances, discounts, or allocations.
- **Open dependency:** OPS.1 must freeze target lifecycle and Job relationship.

### Payment

- **Source identity:** stable provider Payment ID linked to Invoice source identity.
- **Target identity:** `PaymentSourceIdentity` → Enterprise `Payment.id`.
- **Contracts:** phase-2 contracts and provider-neutral `PaymentMigrationRecord`.
- **Required fields:** source/Invoice IDs, status, currency, exact amount.
- **Optional fields:** paid timestamp, method, reference, metadata.
- **Reject/duplicate:** duplicate/existing identity, unresolved Invoice, validation
  failure, incomplete financial detail, monetary imbalance, unsupported lifecycle.
- **Disposition/evidence:** phase-2 financial outcomes, parent and exact-amount
  reconciliation. Payment state or allocation is never inferred.
- **Open dependency:** OPS.1 must freeze Invoice/payment relationships and lifecycle.

### Note

- **Source identity:** SHA-256 of a stable source history-entry ID; parent source ID
  must resolve exactly.
- **Target identity:** immutable `MigrationHistoryEntry.id` linked to an authoritative
  Customer, Service Location, Job, Appointment, Estimate, or Invoice target.
- **Contract:** provider-neutral `HistoryMigrationRecord` in the operational cutover
  foundation. No provider-specific Note transformation is approved here.
- **Required fields:** source ID, supported parent type/source ID, entry type,
  timestamp, nonblank bounded summary, activity category.
- **Optional fields:** employee reference/target, tags, attributes, metadata.
- **Reject/duplicate:** invalid/source-existing identity, missing/wrong-scope parent,
  invalid summary/category, wrong-company employee, unresolved employee reference,
  unsupported tags/attributes retained as evidence.
- **Disposition/evidence:** accepted/rejected/duplicate/unresolved outcome and audit
  summary; unresolved attribution requires review.
- **Open dependency:** authoritative Note source contract and OPS.1 parent/employee
  compatibility remain required.

### Attachment

- **Source identity:** SHA-256 of a stable artifact ID; optional source checksum is
  a duplicate signal, never a replacement identity.
- **Target identity:** migration-owned `MigrationArtifact.id` linked to an exact
  supported parent target; it does not own the operational parent.
- **Contract:** provider-neutral `ArtifactMigrationRecord`; no provider-specific
  Attachment extraction/transfer mapping is approved here.
- **Required fields:** source and parent IDs/type, artifact category, transfer
  outcome; exact parent relationship.
- **Optional fields:** filename, media type, byte size, source/ACP checksums, failure
  classification, cutover-required flag, metadata.
- **Reject/duplicate:** invalid/source-existing identity, checksum duplicate,
  missing/wrong-scope parent, invalid size/filename, retryable/nonretryable transfer
  failure, unavailable source, invalid checksum/validation state.
- **Disposition/evidence:** artifact attempts, transfer/validation state, retry and
  cutover-readiness evidence; no content transfer during MIG.1.
- **Open dependency:** provider extraction/transfer contract and OPS.1 parent/storage
  compatibility must be supplied before freeze.

## Reconciliation and acceptance structure

MIG.1 may freeze only thresholds already enforced by approved contracts:

- source counts reconcile exactly to accepted + rejected + duplicate + unresolved;
- accepted counts equal ordered manifest identities and expected entity counts;
- source, schema, transformation, review, manifest, and replay digests validate;
- unchanged evidence produces identical ordering, UUIDv5 identities where defined,
  SHA-256 digests, classifications, and zero-delta replay;
- source identities and target bindings are unique within Company/provider scope;
- all parent foreign keys resolve in the same Company/Branch scope;
- ambiguity, conflicting cardinality, unresolved owner disposition, unsupported
  schema/lifecycle, and missing evidence fail closed;
- monetary inputs and totals match source evidence exactly; no financial inference;
- immutable pilot boundaries and previously accepted identities remain unchanged;
- required owner-review count is zero only when every item has explicit accepted,
  rejected, duplicate, deferred, or corrected evidence under an approved policy.

No numeric tolerance beyond exact contract equality is introduced. Any requested
tolerance, fuzzy match, lifecycle coercion, default, or merge rule is an owner/product
decision and a stop condition.

## Synthetic validation plan

Use generated UUIDs, digests, names, addresses, timestamps, and money values only.
Do not copy production-like rows or provider payloads.

1. Recompile every entity map twice from permuted synthetic input and prove identical
   canonical output, order, identity, digest, and classification.
2. Exercise valid parent chains from Customer through Payment plus independent Note
   and Attachment parent types.
3. Inject missing IDs/parents/fields, duplicate identities, conflicting targets,
   cross-Company/Branch evidence, ambiguous locations, incompatible statuses,
   monetary imbalance, and unsupported Note/Attachment attributes.
4. Prove every rejected case maps to an existing taxonomy or remains an explicit
   unmapped blocker; never add a catch-all success.
5. Prove owner dispositions are versioned, attributed, append-only, replay-safe, and
   cannot be inferred by technical success.
6. Verify immutable LOCATION.2/SOURCE.5 evidence and CUTOVER.1/CUTOVER.2 readiness
   inputs are read, not rewritten.
7. Run focused and full migration regressions, static checks for touched application
   contracts, Alembic single-head/drift checks, `git diff --check`, and focused
   credential/private-key/raw-source scans.

## PLANNED → READY prerequisites

### Already satisfied

- Customer Migration branch contains accepted LOCATION.2 and SOURCE.5 foundations.
- CUTOVER.1 is owner accepted and remains read-only readiness evidence.
- CUTOVER.2 deterministic planning/rehearsal is complete and pushed.
- CRM.2 is reported complete.
- Existing mapping, manifest, replay, disposition, reconciliation, and tenant-scope
  contracts have been inventoried without changing evidence.
- This preparation package establishes the repository, boundary, stop conditions,
  synthetic validation plan, and commit rules.
- Isolated Migration Alembic lineage has one head: `e0a6c2d8f351`.

### Still required

- OPS.1 must be `OWNER ACCEPTED / COMPLETE`; it is currently `IN PROGRESS` on OM2.
- The complete OPS.1 evidence packet above must be available and internally
  consistent.
- OPS.1-to-Migration comparison must show no semantic ambiguity. Mechanical
  differences may be recorded; semantic conflicts require owner direction.
- Appointment scheduling/dispatch, operational ownership, lifecycle, and parent
  contracts must be frozen from authoritative OPS.1 evidence.
- Estimate and Note/Attachment provider mappings remain blocked unless separately
  authoritative source contracts exist at MIG.1 start.
- Local and remote Migration tips must match at a clean, descendant start SHA.
- Owner must explicitly authorize MIG.1 start after reviewing dependency closure.

Until every required item is satisfied, the only truthful state is
`PLANNED — BLOCKED ON OPS.1`; it is not `READY`.

## Future MIG.1 Start instruction — do not execute now

```text
Start MIG.1 — Freeze migration mapping and reconciliation.

Authoritative dependency evidence:
- OPS.1 status: OWNER ACCEPTED / COMPLETE
- OPS.1 repository: <authoritative repository>
- OPS.1 branch: <authoritative branch>
- OPS.1 commit: <full SHA>
- OPS.1 owner-review evidence: <immutable evidence identity/digest>
- OPS.1 Alembic head: <revision>
- OPS.1 contract packet: <non-sensitive repository path or evidence identity>

Migration repository:
- Worktree: /Users/michaelbfouse/Development/ACP-Enterprise-customer-migration
- Branch: customer-migration-workstream
- Starting SHA: resolve from origin/customer-migration-workstream after fetch;
  require local equality, clean worktree/index, and ancestry from
  b66955f3df5b0daf62ee57d488d5f49e53338942.
- Expected isolated Alembic head: e0a6c2d8f351

Follow docs/deployment/mig-prep-1-mapping-freeze-execution-package.md exactly.
First validate the OPS.1 packet and produce a compatible/changed/missing/conflicting
matrix for all ten launch entities. Stop on any semantic ambiguity, owner/business
decision, migration/schema requirement, immutable-evidence impact, or live-data need.

Freeze only mappings already proven by authoritative contracts. Preserve LOCATION.2,
SOURCE.5, CUTOVER.1, CUTOVER.2, historical evidence, pilot boundaries, deterministic
ordering, replay, Company/Branch isolation, and fail-closed reconciliation.

Use synthetic/no-live-data validation only. Do not import, synchronize, execute
cutover, contact a provider, deploy, or access Preview or Production. Do not infer
identity, parentage, statuses, financial values, or owner approval. Do not begin any
later milestone.
```

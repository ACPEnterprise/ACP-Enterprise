# Mobile Field Backend Gaps 1

## Outcome

This milestone adds one bounded server contract and records the exact ownership of the remaining technician gaps. It does not change Mobile build 0.2.0 (3), create provider integrations, or invent employment, legal, payment, or Inventory policy.

## Gap classification

| Priority | Capability | Classification | Current authority and next boundary |
| --- | --- | --- | --- |
| 1 | Employee-safe Job instructions | `EXISTING_BACKEND_REQUIRES_SMALL_API_ADAPTER` | `Job.customer_reported_problem` has customer-origin semantics. `GET /api/v1/technician/jobs/{job_id}/instructions` now projects it only after current Employee, Company, Branch, and active assignment resolution. Internal Job/Customer/Location text and gate data remain omitted because no field-visibility classification exists. |
| 2 | Employee timecard correction request | `BACKEND_DOMAIN_CAPABILITY_MISSING` | Timekeeping owns audited administrator corrections, immutable revisions, and correction classification. The unintegrated Workforce exception candidate also owns this collision domain. A separate Employee request aggregate/lifecycle is absent; direct self-correction is prohibited. |
| 3 | Follow-up / unable to complete | `EXISTING_BACKEND_NOT_EXPOSED_TO_MOBILE` | The versioned, audited Job pause command already supports `customer_unavailable`, `awaiting_material`, `safety_condition`, `weather`, and `operational_hold`. Existing Job execution guards revalidate technician assignment. The next Mobile candidate may present these reasons against the existing pause endpoint; no parallel status was added. |
| 4 | Photos / attachments | `PROVIDER_REQUIRED` | Assignment-scoped intent/finalize metadata, MIME/size/digest validation, idempotency, append-only evidence, and authorization exist. Protected byte storage, upload tickets, malware/content scanning, and protected retrieval are absent. |
| 5 | Employee notification inbox | `BACKEND_DOMAIN_CAPABILITY_MISSING` | Communications/outbox delivery evidence is not a durable Employee inbox/read-state aggregate. Engineering Control notifications are not Employee product authority. |
| 6 | Technician Estimate authoring | `BACKEND_DOMAIN_CAPABILITY_MISSING` | Estimates support authorized management create/revise and field read-only exact-revision presentation. There is no assignment-scoped technician command boundary or accepted technician discount/terms policy. |
| 7 | Job materials / Inventory consumption | `EXISTING_BACKEND_REQUIRES_SMALL_API_ADAPTER` | Inventory has reservations, allocations, idempotent material issue/reversal, stock movement, and provenance. A technician-assignment projection/permission boundary is absent and Inventory is an active owner collision, so this milestone does not modify it. |
| 8 | APNs/FCM delivery | `PROVIDER_REQUIRED` | A provider-neutral safe notification seam exists. Device registration, credentials, delivery provider, token rotation, and revocation are absent. |
| 9 | Customer signature | `LEGAL_POLICY_REQUIRED` | Customer disposition evidence exists, but no accepted legal meaning, signer verification, document/revision binding, retention, or repudiation policy exists. |
| 10 | Payment collection | `BUSINESS_POLICY_REQUIRED` and `PROVIDER_REQUIRED` | Payment intent/receipt status exists read-only. Technician tender authority, provider choice, card-present handling, cash/check evidence, reversals, offline policy, and PCI boundary are not accepted. |

`NOT_REQUIRED_FOR_INITIAL_FIELD_CLOSED` applies to push delivery, legal signature, and technician payment collection if the owner accepts in-app refresh, non-signature customer disposition, and office-owned collection for the initial rollout. It does not remove their provider/policy gates.

## Employee-safe instructions contract

The response contains only Job ID, current assignment identity/version, Job version, customer-reported problem, Job source timestamp, and an explicit list of omitted unclassified fields. It deliberately excludes `internal_description`, Customer notes/history, Location property notes, gate code, access instructions, financial data, and contact data.

The endpoint accepts no Employee ID. `FieldService._assigned_job` resolves authenticated Membership to active Employee, requires an authorized Branch, and requires a current primary or crew assignment. A guessed foreign Job remains concealed as not found.

The canonical endpoint is `GET /api/v1/technician/jobs/{job_id}/instructions` and uses the existing `COMPANY_JOB_READ` authorization context. This is presentation support only; the server-side assignment check remains decisive.

## Required follow-on contracts

### Employee timecard correction request

Create an immutable request aggregate keyed by Company, Employee, source revision, and idempotency key. Store requested start/end (or domain-supported correction facts), reason, submitted timestamp, state (`pending`, `approved`, `rejected`, `superseded`), reviewer identity/time, and resulting correction revision. Employee endpoints must use self-resolution and never mutate the historical entry. Office review remains protected by Timekeeping correction authority.

### Protected artifacts

Provide private object storage with short-lived upload and retrieval grants bound to Company, Branch, Job, assignment, intent, MIME, byte count, and digest. Require server-side content validation/malware scanning, EXIF policy, quarantine, immutable evidence binding, expiration, audit, and deletion/retention policy. Never accept a client filesystem path or public URL as authority.

### Employee inbox and push

Create a durable Employee-addressed notification aggregate with safe class, opaque target, created/updated timestamps, read state, expiry, deduplication identity, and current-authorization resolution on open. Push remains a hint only. APNs/FCM device registrations must be per User/device/environment, revocable, rotated, and contain no protected lock-screen payload.

### Technician Estimate authoring

Add an assignment-scoped command service that resolves Customer/Location from the assigned Job, accepts active Price Book version identities and quantities, delegates all pricing/tax/discount/version computation to Estimates, and returns an exact draft revision. Require explicit technician permission and accepted discount/terms/presentation policy. Signature remains separate.

### Technician materials

Add an assignment-scoped projection of Job reservations/allocations and a command adapter to Inventory material issue/return. It must resolve actor and Job assignment server-side, use Inventory idempotency/versioning, expose no Company-wide stock or cost, and preserve movement/provenance evidence.

## No schema impact

The instructions projection is read-only over existing Job and Dispatch assignment records. This milestone adds no table, column, migration, provider, credential, deployment, Payroll calculation, Accounting posting, or payment movement.

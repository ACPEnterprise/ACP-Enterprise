# HCP.OPEN-WORK.1 — August 21 Housecall Pro open-work cutover contract

This provider-adapter contract revises the Day‑1 operational boundary without
authorizing broad historical migration. It is synthetic-only preparation: it does
not access Housecall Pro, import data, execute MIG.2, deploy, freeze operations, or
cut over.

## Immutable time and system boundary

The target operational freeze is August 20, 2026 after normal operations in
`America/New_York`. This contract does not invent a clock time. The operator must
bind the owner-approved exact timezone-aware close-of-operations timestamp and
emergency disposition policy to the final export manifest. Cutover is August 21,
2026.

Every in-flight Job must have exactly one evidence-backed disposition:

- completed in Housecall Pro;
- migrate to ACP Enterprise; or
- explicitly held/dispositioned.

Only the migrate disposition enters the manifest. A missing disposition blocks.
The completed and held choices remain explicit excluded evidence. No selected Job
may remain operationally active in Housecall Pro after the freeze; enforcement is
an owner/operator gate, not an action performed by this contract.

## Revised Day‑1 boundary

The operational boundary contains Customer, Contact, Service Location, Employee,
open/in-progress Job, future/in-flight Appointment, required accepted Estimate,
required operational Note, required Attachment, open/unpaid Invoice, and related
Payment/application continuity.

MIG.1's broad historical exclusions remain intact. Estimate, Note, and Attachment
are included only as narrow open-work dependencies:

- Estimate: source status accepted/approved and required to perform or bill a
  selected Job;
- Note: required for open work, safety, access, warranty, or a customer commitment,
  with stable identity, parent, timestamp, and author provenance;
- Attachment: required to perform or prove selected work, with stable identity,
  parent, verified availability, and content checksum.

Nonessential historical records stay archived in Housecall Pro.

## Selection and identity rules

Jobs are selected only from open, in-progress, needs-scheduling, or scheduled
states and require exact Customer and Service Location identities. Appointments
must be scheduled, confirmed, or in progress, have valid timezone-aware scheduling
facts, and belong to a selected Job.

Provider employee identity is SHA-256 represented and must bind authoritatively to
one active Enterprise Employee in the same Company and Branch. Duplicate source
identity, one target Employee claimed by multiple source identities, unresolved
Employee, or cross-tenant evidence blocks. Job/Appointment assignments require a
selected parent and a unique set of fully resolved technician identities; there is
no name-based matching.

Invoices are included only when open/unpaid and attached to selected Jobs. Exact
integer minor units must satisfy `total = paid + balance`. Related payments retain
exact applied and unapplied amounts satisfying `payment = applied + unapplied`.
Accounting state is never inferred.

## Manifest, replay, and reconciliation

The deterministic manifest records Company, Branch, provider/environment,
immutable freeze/cutover, executing code SHA, sorted source artifact checksums,
sorted transformation versions, owner and emergency-policy evidence, ordered
source-identity results, and exact per-entity counts. SHA-256 and UUIDv5 seal its
manifest and replay identities.

Each entity reconciles exactly:

`source = included + excluded + rejected + owner disposition + duplicate`

Source identities are unique within entity type. Replays use the identical
manifest and must recognize existing operational/source identities without
duplicates or count delta. Rejection categories include invalid evidence or
tenant scope, missing/invalid parent, unsupported lifecycle/schedule, unresolved
technician/assignment, incomplete Note provenance, unavailable Artifact,
monetary/application mismatch, and missing in-flight disposition.

## MIG.2 readiness impact

MIG.2 must use this open-work contract in addition to MIG.1, MIG.PREP.2, and
MIG.PREP.3 when rehearsing the August 21 boundary. Its future approved immutable
input must contain the open-work export, technician crosswalk, in-flight
dispositions, required Estimate/Note/Attachment evidence, financial continuity,
and emergency-policy digest.

MIG.2 remains blocked by IC.2 and RPT.3 acceptance, the actual approved immutable
non-production export/environment, completed technician and in-flight disposition
evidence, and separate TYPE C authorization. This contract does not mark MIG.2
ready or authorize any operation.

# MIG.1 — Version 1 launch mapping freeze

This freeze is bound to Enterprise commit
`06ba0f39b85b0eeda7e5a4d1747bb326bd28668a`, Enterprise Alembic head
`t5j7f9b1c386`, and Migration mapping contract
`launch-migration-mapping/v1`.

It is a provider-neutral, synthetic-only mapping and reconciliation contract. It
does not authorize or implement extraction, import, synchronization, cutover,
deployment, or operational-domain mutation.

## Final matrix

| Entity | V1 disposition | Authoritative ownership |
| --- | --- | --- |
| Customer | INCLUDED / UNMAPPED OPTIONAL FIELD | CRM; source identity remains provider- and Company-scoped through SOURCE.5. |
| Contact | INCLUDED / UNMAPPED OPTIONAL FIELD | CRM Customer child. |
| Service Location | INCLUDED / UNMAPPED OPTIONAL FIELD | CRM Customer child; LOCATION.2 native identity is authoritative. |
| Job | INCLUDED / FROZEN | Jobs owns identity and lifecycle. |
| Appointment | INCLUDED / FROZEN | Scheduling owns scheduling facts and lifecycle. |
| Estimate | EXCLUDED FROM V1 BY OWNER | Enterprise Financials target is reserved for a future provider contract. |
| Invoice | INCLUDED / FROZEN | Financials, linked to exact Job identity. |
| Payment | INCLUDED / FROZEN | Financials, linked to exact Invoice identity. |
| Note | EXCLUDED FROM V1 BY OWNER | Provider-neutral history target is reserved for a future source contract. |
| Attachment | EXCLUDED FROM V1 BY OWNER | Provider-neutral artifact target is reserved; no extraction or transfer occurs. |

Every included mapping freezes source identity, target identity, parent owner,
required and optional fields, transformation versions, lifecycle mapping, reject
taxonomy, owner-disposition requirement, reconciliation evidence, replay identity,
Company/Branch scope, and immutable evidence requirements in
`app.customer_migration.launch_mapping`.

## Owner-approved exclusions

Estimate, Note, and Attachment observations always reconcile to
`excluded_by_owner`. They cannot produce mapped fields in Version 1. Their existing
target foundations are preserved without inventing source identities, relationships,
lifecycle, attribution, checksums, availability, or transfer semantics.

## Optional fields deliberately left unknown

The following Enterprise fields are absent from V1 output unless a later approved
source/transformation contract names authoritative evidence:

- Customer: `first_name`, `last_name`, `business_name`, `primary_phone`,
  `secondary_phone`, `email`, `is_vip`;
- Contact: `relationship_or_role`, `can_approve_work`;
- Service Location: `property_type`, `gate_access_instructions`,
  `water_shutoff_location`, `sewer_septic`, `is_primary`.

Absence remains absence. The mapping does not emit `false`, an empty string,
`unknown`, or another fabricated default. Evidence attempting to populate these
fields under V1 fails closed as `unmapped_optional_field_present`.

## Reconciliation invariants

- Provider, entity type, Company, Branch, source identity, and canonical input
  digest form replay identity; evidence and reconciliation use SHA-256 and UUIDv5.
- Native identity wins. Address equality never merges Service Locations.
- Missing parents, duplicate or ambiguous identity, conflicting evidence,
  unsupported lifecycle, wrong tenant scope, and missing owner disposition fail
  closed.
- Existing LOCATION.2, SOURCE.5, owner dispositions, pilot boundaries, CUTOVER.1,
  and CUTOVER.2 evidence remain immutable.
- Invoice and Payment Decimal values pass through exactly. The mapping does not
  infer, quantize, allocate, or reinterpret monetary or accounting state.
- OPS.1 request UUID/UUIDv5 identity belongs to operational intake. It does not
  replace provider Job or Appointment source identity during historical migration.

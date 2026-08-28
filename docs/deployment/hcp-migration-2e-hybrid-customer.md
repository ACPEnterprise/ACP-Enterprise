# HCP.MIGRATION.2E hybrid Customer contract

This milestone admits Housecall Pro Customers from the sealed SOURCE.4 API and
referenced-detail evidence. It does not import business rows.

## Identity and assertions

- `hcp-source4-customer-api/v1` accepts the exact acquired Customer object and
  nested address layouts. `hcp-source4-customer-referenced-detail/v1` accepts
  the same acquired object layout with a distinct assertion kind.
- `cus_` native identity is the only Customer union key. Names, phones, email,
  addresses, dates, and similarity are never identity keys.
- API, referenced-detail, and control assertions retain separate digests and
  conflict evidence. There is no undocumented precedence.
- The Customer control export's `ID` values do not share the acquired API
  `cus_` namespace. No authoritative crosswalk exists, so all 5,248 control
  assertions remain independently retained as `UNRESOLVED_CONTROL_IDENTITY`.
  The prior 822 control-adapter rejections remain explicit control evidence;
  they neither disappear nor reject a valid API/detail Customer.

## Qualified sealed-package result

The immutable read-only qualification recomputed 5,253 listed API identities
plus 43 referenced-but-unlisted details: an authoritative union of 5,296.
All 5,296 provide sufficient parent Customer identity and display evidence for
`PERSISTABLE`. They project to 4,148 Contacts and 5,339 complete native Service
Locations. A further 294 acquired Location assertions remain child exceptions;
they do not reject their parent Customer.

All 5,801 SOURCE.4 Job Customer references resolve to a persistable member of
the authoritative union. Consequently unresolved Customer impact is zero for
2023+ Jobs, open Jobs, current Estimates, and current financial relationships.

## Master and lineage barrier

The future master attestation must bind both
`hybrid_customer_admission_digest` and `customer_parent_closure_digest`.
Customer orchestration rejects any reviewed persistence set that differs from
the persistable hybrid set. Successful Customer lineage records independently
retain API, referenced-detail, and control assertion digests, conflicts,
membership, package identity, admission digest, and parent-closure digest.

The control export is never relabeled as API evidence, missing remains missing,
and no financial or economic assertion is accepted through this contract.

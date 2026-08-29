# BANK.PLAT.006.R1 Tenant-Scoped Outbox Idempotency Repair

## Corrected authority

Notification idempotency is Company-scoped. The authoritative identity is
`(company_id, idempotency_key)`; Branch remains immutable context and an
authorization filter, but it is not part of notification identity. Historical
platform-global rows with no Company retain a separate, globally unique
unscoped namespace.

Exact replay inside one Company resolves the existing intent. Reusing the key
for contradictory facts inside that Company fails closed. The same key may be
used independently by two Companies, and neither replay nor authorized
disposition can select the other Company's row.

## Persistence and producers

Revision `s0j2f4h6k831`, parented from `r9i1e3g5j720`, replaces the former
global constraint with two non-overlapping partial unique indexes. Its preflight
rejects duplicate tenant identities instead of rewriting or deleting intent
history. Downgrade similarly fails closed if tenant reuse can no longer be
represented by the former global constraint.

Communications, identity administration, and protected onboarding now bind
their accepted Company context when enqueueing. Communications also persists
its accepted Branch, source event, channel, recipient reference, and actor
context. Repository replay and operator disposition predicates include Company.

## Preserved boundary

The repair does not change delivery, retry, claim, ambiguity, archival, or
append-only evidence semantics. It does not send a notification, broaden
authorization, mutate source-domain truth, or change Preview or Production.

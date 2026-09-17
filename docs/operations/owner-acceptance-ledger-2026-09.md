# Twelve Hats Beta owner acceptance ledger — remediation batch 1

This ledger records owner findings separately from engineering qualification.
Engineering status never transitions a finding to `OWNER_ACCEPTED`; that state
requires a deployed Beta retest with owner evidence.

| ID | Finding | Environment / reporter | Severity | Owner | Engineering status | Branch / candidate | Schema | Protected / Beta | Retest / acceptance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OA-001 | Price Book landing surface is review-heavy instead of category-first. | `beta.twelve-hats.com` / owner acceptance | P1 | Operations | IMPLEMENTED_NOT_DEPLOYED; category navigation exists in current protected UI | `integration/om2-operations` / current cumulative head | none | Current protected; Beta retest required | RETEST REQUIRED / OPEN |
| OA-002 | Persistent authoritative Price Book search is required across code, name, category, and description. | Beta / owner acceptance | P1 | Operations | IMPLEMENTED_NOT_DEPLOYED; backend-backed search is present | current cumulative head | none | Current protected; Beta retest required | RETEST REQUIRED / OPEN |
| OA-003 | Price Book summary and candidate-review populations are ambiguous. | Beta / owner acceptance | P1 | Operations | IMPLEMENTED_NOT_DEPLOYED; page-scoped labels clarified, candidate populations remain separate | current cumulative head | none | Current protected; Beta retest required | RETEST REQUIRED / INVESTIGATING |
| OA-004 | “Customer option group” is ambiguous owner terminology. | Beta / Michael Fouse | P1 | Operations | IMPLEMENTED_NOT_DEPLOYED; reframed as “Service choice group” | current cumulative head | none | Current protected; Beta retest required | RETEST REQUIRED / OPEN |
| OA-005 | All County customer tax policy must be configurable and company-scoped. | All County policy / owner supplied | P1 | Operations + Accounting | IMPLEMENTED_NOT_DEPLOYED; versioned draft/certification/effective-policy authority integrated | `integration/om2-operations` @ `ab6523326135b3b232274060b186ed215d479c75` / PR #409, worker `ab6523326135b3b232274060b186ed215d479c75` | `q2s4u6w8y0a2` → `o1q9s27h4u0v`; one canonical head | PostgreSQL zero-to-head/current=head and focused tax tests passed; Beta retest required | RETEST REQUIRED / OPEN |
| OA-006 | Good / Better / Best must remain an intelligence presentation contract, not Price Book price tiers. | Owner architectural decision | P1 | Operations + Intelligence | IMPLEMENTED_NOT_DEPLOYED; read-only presentation contract and pricing-tier/membership separation integrated | `integration/om2-operations` @ `ab6523326135b3b232274060b186ed215d479c75` / PR #409, worker `ab6523326135b3b232274060b186ed215d479c75` | none beyond shared #409 migration | Focused separation tests and frontend Price Book qualification passed; Beta retest required | RETEST REQUIRED / OPEN |
| OA-007 | Sellable versioned service memberships and durable customer/property entitlements. | All County brochure / owner supplied | P1 | Operations | IMPLEMENTED_NOT_DEPLOYED; Service Agreement authority, Essential/Plus/Premier policy, version/effective-date eligibility, same-day evidence, and entitlement projection integrated | `integration/om2-operations` @ final cumulative head / PR #408, worker `5b279d81a203ac31ff5df50ece92dd6dc5e71731` | `oa7oa8p9q012` → `q2s4u6w8y0a2`; one canonical head | Fresh PostgreSQL zero-to-head/current=head/check passed; focused membership tests passed; Beta owner retest required | RETEST REQUIRED / OPEN |
| OA-008 | Membership discount plus technician job discount requires auditable manager approval. | All County pricing rule / owner supplied | P1 | Operations | IMPLEMENTED_NOT_DEPLOYED; 10/15/20% membership discounts, dollar/percentage technician proposals, manager approval, revision immutability, and replay safety integrated | `integration/om2-operations` @ final cumulative head / PR #408, worker `5b279d81a203ac31ff5df50ece92dd6dc5e71731` | shared `oa7oa8p9q012` migration | Payment/run DB qualification and membership/pricing tests passed; Beta owner/accountant retest required | RETEST REQUIRED / OPEN |
| OA-009 | Hammer Haag and Jeff Lynn are missing from normal customer experience; population completeness must be proven. | Beta / owner acceptance | Launch-critical | Customer/Migration authority | BLOCKED pending authoritative HCP package and sanctioned reconciliation evidence; no manual customer creation performed | no candidate yet | none | Not deployed by this batch | RETEST REQUIRED / BLOCKED |
| OA-010 | Acceptance finding not included in the supplied batch evidence. | Pending owner intake | TBD | TBD | OPEN | none | TBD | none | RETEST REQUIRED / OPEN |
| OA-011 | Acceptance finding not included in the supplied batch evidence. | Pending owner intake | TBD | TBD | OPEN | none | TBD | none | RETEST REQUIRED / OPEN |
| OA-012 | Acceptance finding not included in the supplied batch evidence. | Pending owner intake | TBD | TBD | OPEN | none | TBD | TBD | RETEST REQUIRED / OPEN |
| OA-013 | Acceptance finding not included in the supplied batch evidence. | Pending owner intake | TBD | TBD | OPEN | none | TBD | TBD | RETEST REQUIRED / OPEN |
| OA-014 | Acceptance finding not included in the supplied batch evidence. | Pending owner intake | TBD | Operations | OPEN; ACP Enterprise Search Standard reference retained for intake | none | TBD | RETEST REQUIRED / OPEN |

## Evidence rules

- No row is `OWNER_ACCEPTED` without a deployed Beta retest and owner evidence.
- Price Book Draft, Held, source provenance, immutable snapshots, and explicit
  activation controls remain unchanged.
- No prices were activated, no customer records were manually created, and no
  Preview or Production deployment was performed by this ledger update.
- OA-009 requires provider-ID-based population reconciliation; names are not
  migration identity keys.

## Workforce Issue #415 evidence

`IMPLEMENTED_NOT_DEPLOYED` / `RETEST REQUIRED` on
`integration/om2-operations` (PR #423, worker
`ab40d7c1db1bbe02a6558a3f909525861efde790`). The timeline now renders the
canonical `Role.name`; no `Role.display_name` field was added. Fresh isolated
PostgreSQL qualification passed, including assigned/revoked role history and
Company-scoped authorization. Beta owner/staff retest remains required; this
row is not owner-accepted.

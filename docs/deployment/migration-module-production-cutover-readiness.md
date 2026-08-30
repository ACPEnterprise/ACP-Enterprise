# Migration module production-cutover readiness

The Migration module is mechanically complete to the non-Production boundary.
Completed HCP rehearsal authority and QBO Development evidence remain immutable;
neither is authorization for a real source acquisition or cutover.

## Capability inventory

| Capability | State |
|---|---|
| HCP sealed acquisition and completed deterministic rehearsal | COMPLETE |
| HCP source identity, lineage, repair generations, replay | COMPLETE |
| HCP open-work selection and final-delta contract | COMPLETE |
| QBO OAuth, sandbox fixture, acquisition, evidence and replay | COMPLETE |
| QBO Production read-only executable | BLOCKED_EXTERNAL |
| Provider-neutral transformation and source authority | COMPLETE |
| Native opening-state validation and rollback-only rehearsal | COMPLETE |
| Cross-source owner decisions for real All County facts | BLOCKED_EXTERNAL |
| Real source freeze/final deltas | BLOCKED_EXTERNAL |
| ACP Production activation/cutover | BLOCKED_EXTERNAL |
| Superseded historical migration branches | SUPERSEDED |

## Go/no-go packet

The final authority packet binds repository SHA, actor, Company/Branch, exact
source manifests, transformation versions, historical window, opening evidence,
entity dispositions, source-freeze evidence, final-delta evidence, and owner
decisions. Every entity reconciles as:

`source = migrated + held + exception + non-applicable + deferred-with-authority`

No source item may disappear. A bounded historical window requires independent
opening evidence. Source freeze and final delta receive separate immutable
digests. Production source authorities and Production activation remain explicit
external gates.

## Recovery

Before activation, abort leaves source evidence and accepted checkpoints intact.
Retry uses the same immutable authority and rejects contradictory manifests.
Interrupted domain work resumes from accepted checkpoints; completed aggregates
are not deleted or replayed blindly. Migration rollback concerns destination
execution state. Business rollback concerns post-activation operations and cannot
promise restoration of external source systems. Source systems remain available
read-only for verification until the separately approved retirement gate.

## Owner decisions still required

- Production QBO credentials, OAuth, real realm, and CompanyInfo authorization;
- real Chart of Accounts and historical-depth window;
- customer, Invoice, Payment, AR/AP, cash/bank, payroll, and tax authority;
- HCP final acquisition and exact freeze time;
- disposition of genuine cross-source conflicts;
- final source freeze, go/no-go, and Production activation.

No real QBO, real HCP cutover, Accounting posting, money movement, tax filing,
Production deployment, or ACP Production mutation is authorized by this packet.

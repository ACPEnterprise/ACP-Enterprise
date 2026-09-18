# ACP / Twelve Hats Full-System Roadmap

## Authority and use

This is the durable Factory 2.0 completion authority. Its machine-readable
companion is [acp_full_system_roadmap.yaml](acp_full_system_roadmap.yaml). The
companion deliberately uses the JSON-compatible subset of YAML 1.2 so every
controller can validate and query it with the standard Python runtime.

This roadmap reconciles the original Version 1 planning architecture, the
Master Milestone Queue, the protected product history, the Owner Acceptance
ledger, and successor discoveries through protected SHA
`b3a1a57e7aa2496f09a441957493ea6a2736c075`. Repository evidence supersedes
stale planning text; it does not turn deployment into acceptance.

For user-facing work:

> CODED != TESTED != MERGED != DEPLOYED != CLOSED

`CLOSED` means a normal Michael, Lianne, or employee workflow works end-to-end
with real Twelve Hats Beta data and its required authority, history, audit, and
replay behavior is present. A non-user-facing milestone may close only when its
explicit final acceptance standard is met.

Nothing here authorizes Production deployment, money movement, Payroll
execution, QBO mutation, catalog activation, employee certification, or a
provider commitment. Those remain separately governed actions.

## Canonical status model

Every item carries independent engineering, protected-integration, Beta, and
owner-acceptance states plus a lifecycle summary. Allowed values are:

`NOT_STARTED`, `ACTIVE`, `ENGINEERING_READY`, `INTEGRATED`, `DEPLOYED_BETA`,
`OWNER_ACCEPTANCE_REQUIRED`, `HUMAN_GATE`, `PROVIDER_GATE`, `BLOCKED`,
`POST_PRODUCTION`, and `CLOSED`.

This separation is intentional. For example, Price Book owner operability is
engineering-ready, protected, and deployed, but remains
`OWNER_ACCEPTANCE_REQUIRED`. Payroll foundations are protected, but real
operational Payroll remains `BLOCKED` because projection-only calculate/close
does not create Payroll authority.

## Original 36-family map

| # | Stable milestone ID | Owning factory | Current lifecycle |
|---:|---|---|---|
| 1 | `PLATFORM.PRODUCTION.FOUNDATIONS` | OM1 | HUMAN_GATE |
| 2 | `UX.PRODUCT.EXPERIENCE.REIMAGINATION.1` | LAPTOP | POST_PRODUCTION |
| 3 | `APPLE.MOBILE.DISTRIBUTION` | LAPTOP | HUMAN_GATE |
| 4 | `WORKFORCE.EMPLOYEE.OPERATIONS` | OM2 | OWNER_ACCEPTANCE_REQUIRED |
| 5 | `PAYROLL.FOUNDATIONS` | OM2 | INTEGRATED |
| 6 | `PAYROLL.REAL.OPERATIONAL.CUTOVER` | OM2 | BLOCKED |
| 7 | `PAYROLL.PAYMENT.SUCCESSORS` | OM2 | POST_PRODUCTION |
| 8 | `MIGRATION.HCP.COMPLETENESS` | OM1 | ACTIVE |
| 9 | `CUSTOMER.MANAGEMENT.COMPLETENESS` | OM2 | ACTIVE |
| 10 | `PRICEBOOK.FOUNDATION` | OM2 | DEPLOYED_BETA |
| 11 | `PRICEBOOK.REALWORLD.COMPLETION` | OM2 | OWNER_ACCEPTANCE_REQUIRED |
| 12 | `ESTIMATES.OPTION.SELLING` | OM2 | ACTIVE |
| 13 | `ESTIMATE.JOB.SNAPSHOT.LINEAGE` | OM2 | OWNER_ACCEPTANCE_REQUIRED |
| 14 | `INVOICE.OPERATIONAL.COMPLETION` | OM2 | ACTIVE |
| 15 | `PAYMENTS.OPERATIONAL.COMPLETION` | OM2 | PROVIDER_GATE |
| 16 | `ACCOUNTING.POSTING` | OM2 | BLOCKED |
| 17 | `ACCOUNTING.REPORTS` | LAPTOP | ACTIVE |
| 18 | `QBO.RETAINED.AUTHORITY.TRANSITION` | OM1 | ACTIVE |
| 19 | `PURCHASING.OPERATIONS` | OM2 | OWNER_ACCEPTANCE_REQUIRED |
| 20 | `INVENTORY.MATERIALS.OPERATIONS` | OM2 | OWNER_ACCEPTANCE_REQUIRED |
| 21 | `ACCOUNTING.NATIVE.OPERATIONS` | OM2 | BLOCKED |
| 22 | `QBO.REPLACEMENT.EXIT` | OM1 | BLOCKED |
| 23 | `DISPATCH.INTELLIGENCE` | LAPTOP | ACTIVE |
| 24 | `COMMUNICATIONS.OPERATIONS` | OM2 | PROVIDER_GATE |
| 25 | `ECONOMICS.BREAKEVEN.INTELLIGENCE` | LAPTOP | OWNER_ACCEPTANCE_REQUIRED |
| 26 | `PRICEBOOK.ECONOMICS` | LAPTOP | ACTIVE |
| 27 | `PRICING.MARKUP.RECOMMENDATIONS` | LAPTOP | POST_PRODUCTION |
| 28 | `BEACON.OPERATIONS` | LAPTOP | OWNER_ACCEPTANCE_REQUIRED |
| 29 | `LUMINARY.OPERATIONS` | LAPTOP | OWNER_ACCEPTANCE_REQUIRED |
| 30 | `LIA.OPERATIONS` | LAPTOP | OWNER_ACCEPTANCE_REQUIRED |
| 31 | `ANALYTICS.MANAGEMENT.REPORTING` | LAPTOP | ACTIVE |
| 32 | `PLATFORM.COMMERCIAL.EXPANSION` | OM1 | POST_PRODUCTION |
| 33 | `SECURITY.CONTINUOUS` | OM1 | ACTIVE |
| 34 | `DEVELOPMENT.FACTORY` | OM1 | ACTIVE |
| 35 | `SYSTEM.END_TO_END.ACCEPTANCE` | OM1 | BLOCKED |
| 36 | `SYSTEM.FULL.COMPLETION` | OM1 | BLOCKED |

The companion retains the original intent through
`original_milestone_number` while its successor/supersession field connects
older codes such as `CRM.2`, `EST.3`, `DISP.2`, `MIG.1`–`MIG.4`, and the old
integration checkpoints to current authority.

## Successor discoveries

The first canonical seed adds the material prerequisites that did not exist as
explicit nodes in the original checklist:

- `PLATFORM.OWNERSHIP.BOUNDARY` — Twelve Hats/future 10:31 control is distinct
  from All County tenant-data ownership.
- `BETA.DOMAIN.ACTIVATION` — the accepted `beta.twelve-hats.com` runtime; this
  is currently the only closed successor node.
- `CUSTOMER.CANONICAL.ADMISSION` and `CUSTOMER.SEARCH.ENTERPRISE` — exhaustive
  exact-provider admission precedes human/fuzzy discovery.
- `WORKFORCE.CANONICAL.BINDING` and `TIMEKEEPING.REAL.ACCEPTANCE` — owner-
  certified real identity precedes Timekeeping and Payroll.
- `PAYROLL.MUTATION.AUTHORITY` and `PAYROLL.PAPER.CHECK.EVIDENCE` — durable
  calculation/close/register authority precedes paper-check recording. Labels
  or projections cannot satisfy these milestones.
- `MEMBERSHIP.DISCOUNT.GOVERNANCE` and `ESTIMATES.TAX.POLICY` — the current
  Estimate successors must pass replay/mutation and human-policy gates.
- `PRICEBOOK.OWNER.OPERABILITY` — deployed category/search work remains open
  until Michael or Lianne physically accepts it.
- `MOBILE.REAL.EMPLOYEE.ROLLOUT` — current code, Apple distribution, certified
  users, and physical-device acceptance are separate facts.
- `LIA.SPOKEN.PRESENCE` — voice identity/model/privacy remains post-Production;
  it does not contaminate the launch-critical LIA path.
- `SECURITY.RELEASE.CURRENTNESS` and
  `DEVELOPMENT.FACTORY.RUNTIME.CURRENTNESS` — candidate-bound security and
  physical factory-loop proof remain continuous obligations.

## Dependency graph

The complete graph is encoded as milestone prerequisites and is validated as
acyclic. Important paths include:

```text
exact Employee binding -> real Timekeeping -> Payroll foundations
-> durable calculation/close -> paper-check evidence -> real Payroll cutover

provider Customer acquisition -> exact Customer admission -> human search
-> Customer/Location/Job context -> Estimate/Invoice/Payment history

Price Book foundation -> owner operability -> real catalog completion
-> Estimate options/tax/discount -> immutable sold snapshot -> Job -> Invoice

Inventory items/receipts -> Job materials -> Purchasing
-> actual material evidence -> Economics -> Luminary

source Accounting evidence -> retained-authority reconciliation
-> Financial Reports -> Economics -> Luminary
```

Unrelated work is deliberately not serialized. Security, Development Factory,
Beta operations, provider-neutral communications, and domain completeness can
advance while Payroll inputs, Apple, Production, or Accounting policy is gated.

## Migration completeness program

Nine explicit children cover Customers, Locations, Jobs, Appointments,
Estimates, Invoices, Payments, Employees, and Attachments/Evidence. Each child
must report all of:

`ACQUIRED`, `RECONCILED`, `NATIVE_BOUND`, `PENDING_ADMISSION`, `HELD`,
`AMBIGUOUS`, `UNEXPLAINED`, and `BETA_OPERABLE`.

Unknown counts remain `REQUIRES_CURRENT_COUNT` or `UNKNOWN_NOT_ZERO`; they never
become zero by omission. `CONNECTED_SUCCESSFULLY`, source acquisition, source
display, and native operational admission are different states.

The current Customer evidence is explicitly systemic: 4,310 accepted legacy
candidates, 2,069 durable legacy bindings, and 2,241 accepted-unbound records.
Hammer Haag has provider ID `147405829` and SOURCE.4 identity
`cus_a09b565a07c14dfa9316cce901d730db` but no native ACP Customer. Jeff Lynn's
exact provider identity remains unresolved. Neither may be manually recreated
to claim completeness.

## Controller pull contract

The canonical query is:

```bash
scripts/factory-roadmap validate
scripts/factory-roadmap list --factory OM2
scripts/factory-roadmap next --factory OM1
scripts/factory-roadmap next --factory OM2
scripts/factory-roadmap next --factory LAPTOP
```

`next` filters by factory, orders P0 through P3, rejects gated/blocked/deferred
items, and requires every prerequisite to be at least engineering-ready and
protected/deployed/accepted as represented by the lifecycle state. The output
contains the stable item, preferred lane, priority, and exact next action.

- OM1E reads the full graph and owns canonical Alembic, protected integration,
  Release, schema/security/platform gates, and cross-factory arbitration.
- OM2E filters `owning_factory=OM2`, continuously feeds OM2-A/B/C, and hands
  qualified cumulative Operations heads to OM1E.
- LaptopE filters `owning_factory=LAPTOP`, continuously feeds Laptop-A/B/Phone,
  and keeps P3 intelligence out of the P0 train absent a concrete dependency.
- OM1-A/B/C filter OM1 items by preferred lane and continue independently when
  another item is human/provider/dependency gated.

When evidence changes a prerequisite, the discovering lane adds a stable item
or graph edge and evidence reference in the same protected PR. Integration and
Beta deployment update only their fields. Acceptance feedback advances or
reopens owner state. `CLOSED` is never inferred from a commit or PR count.

## UX friction queue

The machine companion contains a durable queue with required fields for screen,
task, friction, expected behavior, severity, desktop/mobile surface, treatment,
owner, evidence, and state. It currently records Price Book discovery, missing
Customers, Employee timeline/readiness, and Estimate context/policy friction.

The queue feeds `UX.PRODUCT.EXPERIENCE.REIMAGINATION.1`; it does not authorize
the broad redesign. A bounded P0/P1 defect remains owned and repairable in its
current domain.

## Current gates and priorities

Current P0 engineering work is Customer canonical admission/search, durable
Payroll calculation/close/paper-check authority, Membership/discount replay
governance, and exact Employee/migration identity. Price Book and Workforce
have deployed P0 paths awaiting physical retest. Current P1 work includes
per-domain migration completeness, Invoice/Dispatch/connectivity, Mobile
rollout, LIA context, Release Security currentness, and Development Factory
runtime currentness.

Human gates include exact roster/compensation/tax/price/policy certification,
physical owner/employee acceptance, Apple custody/distribution, and platform
ownership/authority decisions. Provider gates include permanent Production,
live payments, communications delivery, OCR, push, ACH/direct deposit, and
other separately approved external services.

## Maintenance rule

Every protected reconciliation that materially changes a milestone must update
the companion's state, evidence, next action, and
`last_reconciled_protected_sha`, then run:

```bash
scripts/factory-roadmap validate
```

Factory telemetry may project this authority and append durable events, but it
must not silently rewrite repository authority or infer completion from Git
activity.

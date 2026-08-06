# Version 1.0 Enterprise Implementation Roadmap

## Authority, scope, and status

This roadmap is the Phase 2 planning architecture from the repository state at
`7ebad9c90c7d511c0cca82395ef4210b0deea750` through ACP Enterprise Version 1.0.
It is incorporated into the [Master Milestone Queue](master-milestone-queue.md)
by `MMQ.4`. It refines the [Module Map](../architecture/module-map.md),
[Platform Roadmap](../architecture/roadmap.md),
[Version 1.0 Release Plan](../product/release-plan.md), and
[Production Readiness Checklist](../product/launch-checklist.md).

Every milestone below is planning architecture, not execution approval. Except
for separately recorded active or completed work in the Master Milestone Queue,
all catalog entries are `PLANNED`. A suggested machine is a capacity forecast,
not an assignment. The owner must approve a milestone definition, repository,
exact starting commit, branch or workspace, migration ownership, acceptance
evidence, and Start before implementation.

Version 1.0 replaces the launch-critical Housecall Pro operating path. QuickBooks
remains the accounting system of record. General ledger, accounts payable,
payroll, bank reconciliation, financial close, broad autonomous AI, and
multi-company SaaS administration are not Version 1.0 claims. Production remains
untouched until the independent release gates are approved.

## Planning assumptions

- Current active milestones remain `EST.2`, `INV.1`, `CUTOVER.1`, and Business
  Economics Phase 7; this roadmap does not change their status or assert their
  completion.
- Existing Customer, Scheduling, Jobs, Dispatch, Price Book, Platform, event,
  notification, Development Factory, Mission Control, and early Analytics
  foundations are reused rather than re-created.
- `t5j7f9b1c386` is the current single repository Alembic head. Any future schema
  milestone receives one owner and is integrated serially onto the then-accepted
  head.
- “Office Machine 2” remains distinct from the active assignment label “Machine
  2” until the owner reconciles them.
- Complexity is relative: `S` is bounded configuration or projection work, `M`
  is one coherent vertical slice, `L` spans several layers or an external
  integration, and `XL` is a launch-critical cross-system proof.

## Version 1.0 milestone catalog

### Phase 1 — Converge foundations and launch contracts

| Code | Purpose | Scope | Prerequisites | Expected outputs | Integration points | Implementation | Validation | Expected repository | Suggested machine |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `CRM.2` | Close launch CRM gaps | Intake, contacts, service locations, deduplication, notes, consent-safe history | Existing Customer and Location foundations | Approved CRM contract, APIs, UI, events, deduplication evidence | Scheduling, Jobs, Communications, Portal, Migration | `L` | `L` | `ACP-Enterprise`, isolated worktree | Office Machine 2 after identity confirmation |
| `OPS.1` | Complete launch job lifecycle | Service request, job, appointment handoff, cancellation, reschedule, exceptions | `CRM.2`; existing Scheduling and Jobs foundations | End-to-end office workflow, state rules, events, acceptance tests | CRM, Dispatch, Technician, Estimates, Financial | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 1 after `EST.2` handoff |
| `DISP.2` | Complete dispatch execution | Availability projection, assignment workflow, arrival states, exceptions | `OPS.1`; Dispatch Assignment V1 | Launch dispatch board, assignment APIs, events, dispatcher evidence | Operations, Workforce, Technician, Communications | `L` | `L` | `ACP-Enterprise`, isolated worktree | Office Machine 2 |
| `EST.3` | Make estimates launch-ready | Options, discounts, approval evidence, conversion, responsive UX | `EST.2`; `CRM.2` | Accepted estimate journey and immutable authorization evidence | Price Book, Jobs, Technician, Portal, Invoicing | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 1 |
| `INV.2` | Complete inventory control core | Locations, on-hand balances, adjustments, reservations, transfers | `INV.1`; `OPS.1` | Inventory services, APIs, UI, events, concurrency tests | Purchasing, Technician, Jobs, Reporting | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 2 |
| `PUR.1` | Establish purchasing foundation | Vendors, purchase orders, lifecycle, authorization boundaries | Inventory & Purchasing Architecture V1; `INV.2` | Vendor and PO domain, repository, APIs, audit events | Inventory, Financial, Reporting | `L` | `L` | `ACP-Enterprise`, isolated worktree | Office Machine 1 |
| `TECH.1` | Establish technician application shell | Role-scoped itinerary, job context, navigation, responsive and accessible shell | `OPS.1`; `DISP.2`; Platform identity | Technician shell, route guards, API contracts, device acceptance | Jobs, Dispatch, CRM, Communications | `M` | `L` | `ACP-Enterprise`, isolated worktree | Office Machine 2 |
| `COMMS.1` | Establish launch communications | Provider boundary, consent, templates, delivery history, retry contract | `CRM.2`; notification outbox | Messaging service boundary, delivery records, failure handling | CRM, Operations, Estimates, Financial, Portal | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 1 |
| `BE.8` | Define Version 1.0 economics contract | KPI definitions, attribution, profitability inputs, QuickBooks boundary | Business Economics Phase 7 | Approved KPI catalog, ownership map, reconciliation tolerances | Reporting, Estimates, Jobs, Financial | `M` | `M` | Business Economics Repository | Business Economics capacity |
| `MIG.1` | Freeze migration mapping and reconciliation | Launch entities, field maps, transforms, reject taxonomy, thresholds | `CUTOVER.1`; `CRM.2`; `OPS.1` contracts | Versioned mapping, synthetic dataset, reconciliation plan | CRM, Operations, Estimates, Financial, Reporting | `L` | `XL` | Migration Repository | Migration capacity |
| `PLAT.1` | Close launch platform controls | Role matrix, branch enforcement, audit access, secrets and support boundaries | Existing Platform and security foundations | Accepted launch-role matrix, tenant tests, audit and support runbooks | Every protected module | `M` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 1 |
| `IC.1` | Integrate launch foundations | Review and serialize Phase 1 accepted outputs | `CRM.2`; `OPS.1`; `DISP.2`; `EST.3`; `INV.2`; `PUR.1`; `TECH.1`; `COMMS.1`; `BE.8`; `MIG.1`; `PLAT.1` | One reviewed commit set, one Alembic head, aggregate validation report | All Phase 1 boundaries | `L` | `XL` | `ACP-Enterprise` integration workspace | Laptop 1 |

### Phase 2 — Revenue, field execution, and customer experience

| Code | Purpose | Scope | Prerequisites | Expected outputs | Integration points | Implementation | Validation | Expected repository | Suggested machine |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `TECH.2` | Enable field work execution | Status, notes, photos, forms, customer approvals, completion evidence | `TECH.1`; `EST.3`; `IC.1` | Executable field journey, durable evidence, role and branch tests | Jobs, Dispatch, Estimates, Communications | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 2 |
| `INV.3` | Capture job materials | Issue, return, consumption, reservation release, correction audit | `INV.2`; `TECH.2` | Material ledger and job consumption workflow | Technician, Jobs, Purchasing, Invoicing, Reporting | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 1 |
| `PUR.2` | Receive and reconcile purchases | Receipts, partial receipts, discrepancies, stock updates | `PUR.1`; `INV.2`; `IC.1` | Receiving workflow, inventory postings, exception evidence | Inventory, Financial, Reporting | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 2 |
| `PUR.3` | Add replenishment controls | Reorder thresholds, recommendations, approval, PO linkage | `PUR.2`; `INV.3` | Replenishment queue and auditable recommendations | Inventory, Business Economics, Beacon | `M` | `L` | `ACP-Enterprise`, isolated worktree | Office Machine 1 |
| `INV.4` | Prove inventory launch readiness | Counts, transfer/adjustment reconciliation, permissions, performance | `INV.3`; `PUR.3` | Reconciliation report, role evidence, accepted exceptions | Migration, Reporting, Release | `M` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 2 |
| `INVOICE.1` | Establish operational invoicing | Invoice facts, lines, tax boundary, totals, lifecycle, events | `EST.3`; `OPS.1`; `IC.1` | Invoice domain, repository, APIs, deterministic calculations | Estimates, Jobs, Inventory, Payments, Accounting | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 1 |
| `INVOICE.2` | Deliver invoice workflow | Generate from accepted work, present, send, receipt state, UI | `INVOICE.1`; `TECH.2`; `COMMS.1` | Office, technician, and customer invoice journey | Technician, Communications, Portal, Payments | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 2 |
| `INVOICE.3` | Add controlled corrections | Void, adjustment, credit boundary, audit trail, balance recomputation | `INVOICE.2` | Correction workflows and immutable financial evidence | Payments, Accounting, Reporting | `M` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 1 |
| `PAY.1` | Establish payment provider boundary | Tokenization, idempotency, request/attempt model, webhook verification | `INVOICE.1`; `PLAT.1` | Provider adapter contract, threat model, failure-safe persistence | Invoicing, Platform, Communications | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 2 |
| `PAY.2` | Collect and record payments | Payment request, charge/record flow, receipts, retries | `PAY.1`; `INVOICE.2` | Payment journey with duplicate-charge protection | Invoicing, Portal, Technician, Communications | `XL` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 1 |
| `PAY.3` | Reconcile refunds and failures | Refunds, failed/late webhooks, settlement exceptions, correction rules | `PAY.2`; `INVOICE.3` | Reconciliation queue, refund evidence, recovery tests | Accounting, Reporting, Beacon | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 2 |
| `ACC.1` | Define QuickBooks handoff | Operational-to-accounting mapping, export ownership, idempotent references | `INVOICE.3`; `PAY.3`; `BE.8` | Approved QuickBooks contract and financial control matrix | Invoicing, Payments, Business Economics | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 1 with finance review |
| `ACC.2` | Implement accounting reconciliation | Export/integration, acknowledgements, retry, variance workflow | `ACC.1` | QuickBooks handoff, reconciliation report, exception ownership | Reporting, Migration, Beacon | `XL` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 1 with finance review |
| `PORTAL.1` | Establish customer portal trust boundary | Customer authentication, account linking, consent, tenant isolation | `CRM.2`; `PLAT.1`; `IC.1` | Portal identity architecture, APIs, shell, security tests | CRM, Platform, Communications | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 2 |
| `PORTAL.2` | Expose commercial self-service | Estimate review/approval, invoice view, payment request and receipt | `PORTAL.1`; `EST.3`; `INVOICE.2`; `PAY.2` | Customer commercial journey and accessibility evidence | Estimates, Invoicing, Payments, Communications | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 2 |
| `PORTAL.3` | Expose appointment self-service | Appointment view, bounded reschedule/cancel request, message history | `PORTAL.1`; `OPS.1`; `COMMS.1` | Customer appointment journey and safe request handoff | Scheduling, Operations, Communications | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 1 |
| `COMMS.2` | Complete launch notification journeys | Appointment, dispatch, estimate, invoice, payment, receipt templates | `COMMS.1`; `DISP.2`; `EST.3`; `INVOICE.2`; `PAY.2` | Approved templates, consent tests, delivery observability | All customer-facing workflows | `M` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 2 |
| `IC.2` | Integrate revenue and experience | Serialize accepted Phase 2 migrations and contracts | `TECH.2`; `INV.3`; `PUR.2`; `PUR.3`; `INV.4`; `INVOICE.3`; `PAY.3`; `ACC.2`; `PORTAL.2`; `PORTAL.3`; `COMMS.2` | One head, full booked-to-cash journey, financial reconciliation evidence | All Phase 2 boundaries | `XL` | `XL` | `ACP-Enterprise` integration workspace | Laptop 1 |

### Phase 3 — Intelligence, economics, migration proof, and operations

| Code | Purpose | Scope | Prerequisites | Expected outputs | Integration points | Implementation | Validation | Expected repository | Suggested machine |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `RPT.1` | Establish launch reporting projections | Versioned projections for customers, work, revenue, exceptions | `IC.2`; `BE.8` | Projection contracts, rebuild path, freshness metrics | Events, CRM, Operations, Financial | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 1 |
| `RPT.2` | Deliver operational dashboards | Schedule, dispatch, technician, conversion, revenue, exception views | `RPT.1` | Tenant-scoped dashboards, drill-down, accessibility evidence | Beacon, Business Economics, Mission Control | `L` | `L` | `ACP-Enterprise`, isolated worktree | Office Machine 2 |
| `RPT.3` | Deliver launch reports and exports | Finance handoff, reconciliation, migration, support and audit exports | `RPT.1`; `ACC.2`; `INV.4` | Approved reports, export controls, total reconciliation | Accounting, Migration, Release | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 1 |
| `BE.9` | Validate launch economics | KPI calculations, profitability views, source-to-report reconciliation | `BE.8`; `RPT.1`; `ACC.2` | Accepted economics dashboard and variance evidence | Reporting, Beacon, finance review | `M` | `XL` | Business Economics Repository | Business Economics capacity |
| `BEA.6` | Surface bounded operational exceptions | Owner-visible signals for launch-critical failures; no autonomous action | `RPT.1`; existing Beacon foundation | Reviewed exception catalog, signals, acknowledgement audit | Reporting, Communications, Mission Control | `M` | `L` | `ACP-Enterprise`, isolated worktree | Office Machine 2 |
| `BEA.7` | Add launch health summaries | Revenue, migration, integration, outbox and support health summaries | `BEA.6`; `RPT.2`; `BE.9` | Owner summary with source links and stale-data behavior | Reporting, Business Economics, Release | `M` | `L` | `ACP-Enterprise`, isolated worktree | Office Machine 2 |
| `AUTO.1` | Add bounded launch automation | Approved notification and exception rules only; no autonomous money or schedule decisions | `COMMS.2`; `BEA.6`; `PLAT.1` | Rule audit, retries, kill switch, authorization tests | Communications, Beacon, module APIs | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 1 |
| `MIG.2` | Execute representative dry run | Import production-shaped non-production data and classify exceptions | `MIG.1`; `IC.2`; `RPT.3` | Timed run, counts, reject ledger, remediation plan | Every launch data owner | `XL` | `XL` | Migration Repository | Migration capacity |
| `MIG.3` | Prove repeatable migration | Second dry run, delta strategy, rollback decision points, reconciliation | `MIG.2`; `BE.9`; `BEA.7` | Repeatability evidence, approved thresholds, cutover candidate | Reporting, Beacon, Accounting, Release | `XL` | `XL` | Migration Repository | Migration capacity |
| `TECH.3` | Complete technician closeout | Materials, signatures, required forms, completion and invoice handoff | `TECH.2`; `INV.3`; `INVOICE.2` | Accepted arrival-to-closeout field journey | Inventory, Invoicing, Communications | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 2 |
| `TECH.4` | Harden technician experience | Degraded-network safety, retries, stale state, performance, accessibility | `TECH.3`; `COMMS.2` | Device matrix, recovery evidence, support playbook | Platform, Support, Release | `L` | `XL` | `ACP-Enterprise`, isolated worktree | Office Machine 1 |
| `IC.3` | Integrate Version 1.0 candidate | Integrate intelligence, migration, automation, and field hardening | `RPT.2`; `RPT.3`; `BE.9`; `BEA.7`; `AUTO.1`; `MIG.3`; `TECH.4` | Immutable candidate, one head, full regression and traceability | All Version 1.0 modules | `XL` | `XL` | `ACP-Enterprise` integration workspace | Laptop 1 |

### Phase 4 — Preview, cutover readiness, and Version 1.0 release gates

| Code | Purpose | Scope | Prerequisites | Expected outputs | Integration points | Implementation | Validation | Expected repository | Suggested machine |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `IC.4` | Validate production-like preview | Deploy only to separately approved preview, run security, performance, backup/restore and journeys | `IC.3` | Preview evidence, defect ledger, rollback proof; no Production change | Deployment, every launch workflow | `L` | `XL` | `ACP-Enterprise` integration workspace | Laptop 1 |
| `MIG.4` | Prepare immutable cutover package | Final extraction/import plan, checksums, reconciliation, rollback and authorities | `MIG.3`; `IC.4` | Owner-reviewable cutover package; no execution authorization | Housecall Pro, QuickBooks, Release | `L` | `XL` | Migration Repository | Migration capacity |
| `REL.1` | Run controlled pilot | Selected non-production or separately approved pilot scope, training and support rehearsal | `IC.4`; `MIG.4` | Pilot evidence, support metrics, classified gaps | Operations, finance, support, vendors | `L` | `XL` | `ACP-Enterprise` integration workspace | Laptop 1 |
| `REL.2` | Close Version 1.0 readiness | Resolve blockers and assemble product, security, finance, migration and operations evidence | `REL.1`; `RPT.3`; `TECH.4`; `ACC.2` | Completed readiness dossier and explicit residual-risk decisions | Production Readiness Checklist | `M` | `XL` | `ACP-Enterprise` | Laptop 1 |
| `IC.5` | Obtain Version 1.0 go/no-go | Independent owner review of immutable release, migration package and rollback | `REL.2` | Explicit go/no-go record; passing does not itself deploy | Executive, product, engineering, operations, finance | `S` | `XL` | `ACP-Enterprise` | Laptop 1 |
| `REL.3` | Execute separately approved release | Reserved release action after explicit Production authorization | `IC.5`; separate Production approval | Version 1.0 release record, smoke tests, monitoring and rollback disposition | Production and external providers | `XL` | `XL` | `ACP-Enterprise` release workspace | Laptop 1 |

## Dependency graph and implementation order

The graph is a directed acyclic planning model. Each integration checkpoint
serializes accepted work before the next phase. It does not authorize a merge,
deployment, or milestone Start.

```text
Current active work: EST.2   INV.1   CUTOVER.1   Economics Phase 7
                         │      │         │              │
                         └──────┴─────────┴──────────────┘
                                      │
Phase 1: CRM.2 → OPS.1 → DISP.2 ───────────────┐
         CRM.2 → EST.3                          │
         OPS.1 → INV.2 → PUR.1                  ├→ IC.1
         OPS.1 + DISP.2 → TECH.1                │
         CRM.2 → COMMS.1; Phase 7 → BE.8        │
         CUTOVER.1 → MIG.1; Platform → PLAT.1 ──┘
                                      │
Phase 2: TECH.1 + EST.3 → TECH.2 → INV.3 → INV.4 ─┐
         INV.2 → PUR.2 → PUR.3 ────────────────────┤
         EST.3 + OPS.1 → INVOICE.1 → .2 → .3       ├→ IC.2
         INVOICE.1 → PAY.1 → PAY.2 → PAY.3          │
         INVOICE.3 + PAY.3 → ACC.1 → ACC.2          │
         PLAT.1 → PORTAL.1 → PORTAL.2 / PORTAL.3 ───┤
         COMMS.1 → COMMS.2 ─────────────────────────┘
                                      │
Phase 3: IC.2 → RPT.1 → RPT.2 / RPT.3 ─────────────┐
         BE.8 + RPT.1 + ACC.2 → BE.9                │
         RPT.1 → BEA.6 → BEA.7; BEA.6 → AUTO.1      ├→ IC.3
         MIG.1 + IC.2 → MIG.2 → MIG.3               │
         TECH.2 + INV.3 + INVOICE.2 → TECH.3 → .4 ──┘
                                      │
Phase 4: IC.3 → IC.4 → MIG.4 → REL.1 → REL.2 → IC.5 → REL.3
```

## Recommended parallel execution plan

Parallel work requires isolated repositories or worktrees, non-overlapping file
ownership, and no competing migration parent. Integration and migration edits
remain serialized even where discovery, UI, tests, or documentation can run in
parallel.

| Wave | Parallel-safe candidates after prerequisites | Required serialization |
| --- | --- | --- |
| 0 — current | Existing `EST.2`, `INV.1`, `CUTOVER.1`, and Economics Phase 7 remain isolated | Owner chooses `EST.2`/`INV.1` lineage order; Laptop 1 integrates one accepted commit set at a time |
| 1A | `CRM.2`, `BE.8`, `PLAT.1`, and migration mapping discovery for `MIG.1` | Any schema revisions; `MIG.1` cannot freeze until `CRM.2`/`OPS.1` contracts settle |
| 1B | `EST.3`, `OPS.1`, and `COMMS.1` after `CRM.2`; `INV.2` after `OPS.1` | Shared CRM/Jobs contracts and Alembic lineage; `IC.1` is single-file-order integration |
| 1C | `DISP.2`, `PUR.1`, and `TECH.1` after their prerequisites | Dispatch/Technician shared interfaces; `IC.1` aggregate validation |
| 2A | `TECH.2`, `PUR.2`, `INVOICE.1`, `PAY.1`, and `PORTAL.1` on isolated boundaries | Invoice/Payment schema order and shared financial contracts |
| 2B | `INV.3`, `INVOICE.2`, `PORTAL.3`; then `PUR.3`, `INVOICE.3`, `PAY.2`, `PORTAL.2` as edges clear | Financial totals, provider webhooks, portal authorization, and Alembic chain |
| 2C | `INV.4`, `PAY.3`, `COMMS.2`; then `ACC.1` and `ACC.2` | QuickBooks mapping and financial reconciliation; `IC.2` serial integration |
| 3A | `RPT.1`, `MIG.2`, and `TECH.3`; then `RPT.2`, `RPT.3`, `BE.9`, `BEA.6` | Projection schemas, migration datasets, and source-of-truth definitions |
| 3B | `BEA.7`, `AUTO.1`, `MIG.3`, and `TECH.4` after dependencies | Automation approval surfaces; `IC.3` serial candidate assembly |
| 4 | Training/support preparation may accompany `IC.4` and `MIG.4` evidence work | `IC.4`, `MIG.4`, `REL.1`, `REL.2`, `IC.5`, and `REL.3` are a strict release chain |

### Always serialized

- Every accepted Alembic revision onto the shared Enterprise head.
- Invoice, payment, refund, QuickBooks export, and reconciliation contract
  changes that affect the same financial fact or idempotency key.
- Migration mapping freeze, dry runs, final package, and any cutover execution.
- Integration checkpoints `IC.1` through `IC.5` and release milestones.
- Shared authorization, tenant, event-envelope, public API, and deployment
  contract changes.
- Any Production action, which remains outside this roadmap until explicitly
  approved.

## Integration checkpoints

| Checkpoint | Admission evidence | Exit evidence |
| --- | --- | --- |
| `IC.1` | Owner-accepted Phase 1 milestones, exact commits, clean handoffs, migration parents | One head, foundation contract tests, role/tenant tests, representative import skeleton |
| `IC.2` | Accepted Phase 2 slices and provider test credentials in an approved non-production boundary | Booked-to-cash journey, material and financial reconciliation, retry/idempotency proof |
| `IC.3` | Accepted reporting, economics, Beacon, automation, migration, and technician hardening | Immutable Version 1.0 candidate, full regression, requirements traceability |
| `IC.4` | Separately approved preview target, candidate, migration and rollback plans | Production-like journey, security, performance, backup/restore and observability evidence |
| `IC.5` | Closed launch checklist blockers, pilot evidence, immutable cutover and rollback packages | Explicit multidisciplinary go/no-go; Production still requires its own action approval |

## Architecture risks

| Risk | Exposure | Required mitigation / decision |
| --- | --- | --- |
| Active-work truth is incomplete | `EST.2`, `INV.1`, `CUTOVER.1`, and Phase 7 lack exact handoff commits and acceptance boundaries | Reconcile each external repository before pulling roadmap work |
| Alembic collision | Parallel schema work can fork `t5j7f9b1c386` or a later head | One migration owner at a time; record intended parent; serial integration and disposable-database proof |
| Financial source-of-truth ambiguity | Operational totals can diverge from QuickBooks or provider settlement | Approve immutable ownership, rounding/tax, idempotency and reconciliation contracts before `INVOICE.1`/`PAY.1` |
| Payment security and duplicate charge risk | Webhooks, retries, tokens, and partial failures are financially consequential | Tokenization, verified webhooks, idempotency keys, least privilege and failure-injection evidence |
| Customer portal identity | Account linking can expose another customer or company | Separate portal trust model, tenant-bound claims, enumeration resistance and security review before `PORTAL.2` |
| Technician degraded connectivity | Field state may be stale, duplicated, or lost | Versioned commands, retry-safe writes, visible freshness and bounded Version 1.0 degraded behavior |
| Cross-module cycles | Field, inventory, financial and communications workflows consume each other | Stable application interfaces and events; prohibit cross-module table writes |
| Event/projection drift | Reports, Beacon, and automations may disagree with authoritative modules | Versioned events, replay/rebuild, freshness indicators and source-linked drill-down |
| Migration quality and coexistence | Source duplicates and mid-cutover changes can corrupt relationships | Repeatable imports, delta policy, reject ledger, thresholds, freeze authority and rollback rehearsal |
| External provider reliability | Messaging, payments, mapping and QuickBooks can fail or throttle | Provider adapters, timeouts, retries, circuit/queue behavior, observability and manual recovery |
| Authorization catalog growth | New routes may omit branch or role enforcement | Permission catalog review and negative tenant/branch tests at each checkpoint |
| Scope conflict with Version 1.0 | Full accounting, broad AI, offline-first and SaaS work can enter the launch path | Enforce deferred list and require a new owner-approved milestone for expansion |
| Beacon product boundary | Repository foundation exists, but launch exception semantics and authority need approval | Keep Beacon read/advisory for 1.0; no autonomous operational or financial mutation |
| Luminary definition | No authoritative Luminary architecture is present in this baseline | Defer implementation; approve purpose, data, trust and overlap with Beacon before planning code |
| Operational LIA authority | Engineering automation could exceed owner gates or touch product runtime | Preserve Development Factory isolation and explicit owner approval for every privileged action |
| Release forecast uncertainty | No calibrated throughput, staffing or active-work completion dates were supplied | Forecast in dependency waves and ranges; reforecast after every checkpoint |

## Implementation forecast

These are elapsed engineering ranges after the active-work handoffs are accepted,
assuming two isolated product capacities, one migration capacity, one economics
capacity, and Laptop 1 for serialized integration. They are estimates, not dates
or commitments. A single product capacity or unresolved architecture decisions
will extend the range.

| Forecast stage | Expected elapsed range | Completion signal |
| --- | --- | --- |
| Active-work reconciliation and Phase 1 | 3–5 weeks | `IC.1` accepted with one head and stable launch contracts |
| Phase 2 revenue and experiences | 5–8 additional weeks | `IC.2` accepted with reconciled booked-to-cash journey |
| Phase 3 intelligence and migration proof | 3–5 additional weeks | `IC.3` accepted as immutable Version 1.0 candidate |
| Phase 4 preview and release readiness | 2–4 additional weeks | `IC.5` go/no-go record with no unresolved blocker |
| Total to Version 1.0 readiness | 13–22 weeks after active-work reconciliation begins | Approved release candidate and cutover package; deployment remains separate |

Reforecast when an active milestone completes, a provider is selected, migration
volume is profiled, or an integration checkpoint fails. Never compress financial,
security, tenant-isolation, migration, backup/restore, or rollback validation to
meet a forecast.

## Future backlog and deferred milestones

Backlog items are unsequenced candidates. Deferred milestones have a deliberate
post-Version 1.0 boundary and may not enter the Version 1.0 critical path without
an approved scope change.

### Backlog

| Candidate | Earliest dependency | Reason not sequenced |
| --- | --- | --- |
| Memberships and recurring service | Stable Jobs, Payments, Communications | Launch-critical workflow inventory has not approved it for Version 1.0 |
| Route and capacity optimization | `DISP.2`; reliable travel inputs | Provider choice and operational acceptance criteria are undefined |
| Advanced estimate financing and sales coaching | `EST.3`; `PAY.3` | Financing, compliance and business ownership are undefined |
| Warranty and equipment history depth | `TECH.3`; CRM asset model | Launch-critical data and workflow scope are not approved |
| Campaign and attribution depth | `CRM.2`; `RPT.1` | Marketing-source and consent architecture needs separate approval |

### Deferred

| Code | Milestone | Earliest release | Reason |
| --- | --- | --- | --- |
| `ACC.GL.1` | Double-entry general ledger and period controls | Version 2.0 | QuickBooks remains Version 1.0 accounting system of record |
| `ACC.AP.1` | Accounts payable, vendor bills and disbursements | Version 2.0 | Requires accounting controls and segregation of duties |
| `ACC.CLOSE.1` | Bank reconciliation, close and formal statements | Version 2.0 | Requires sustained parallel financial validation |
| `INV.5` | Predictive replenishment and multi-location optimization | Version 1.5 | Not required for launch material tracking |
| `TECH.5` | Offline-first field synchronization | Version 1.5 | Version 1.0 provides bounded degraded-network behavior only |
| `PORTAL.4` | Broad customer account self-service | Version 1.5 | Version 1.0 is limited to launch journeys |
| `BEA.8` | Autonomous operational remediation | Post-1.0 | Beacon remains read/advisory at launch |
| `LUM.1` | Luminary domain and trust architecture | Post-1.0 | No authoritative product boundary exists in the current architecture |
| `LUM.2` | Luminary advisory implementation | Post-`LUM.1` | Scope, data authority, safety and overlap with Beacon are unresolved |
| `LIA.1` | Operational isolated-worker launcher | Post-1.0 engineering platform | Current LIA is advisory and cannot execute parallel workers |
| `LIA.2` | Remote owner approval and notification flow | Post-`LIA.1` | Must preserve owner gates, isolation, redaction and no self-integration |
| `SAAS.1` | Multi-company provisioning and platform billing | Version 3.0 | Single-company Version 1.0 must not be delayed by SaaS administration |

## Roadmap change control

The Master Milestone Queue remains the operational status authority. Changes to
this roadmap require owner review and must keep codes unique, dependencies
acyclic, phase and parallel groups consistent, Version 1.0 scope explicit, and
integration checkpoints intact. Moving a roadmap entry to `READY` requires a
separate queue update with the complete execution contract; the roadmap itself
grants no Start, Git, deployment, migration-execution, or Production authority.

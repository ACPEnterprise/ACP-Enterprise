# ECO launch evidence validation 1 — Enterprise integration packet

Date: 2026-09-12

## Authority and boundary

- Protected starting authority: `origin/customer-management-v1` at `b22297c65165280a761860198dc05441df4a4312`.
- Qualified branch: `work/eco-launch-evidence-validation-1`.
- This change adds no migration, policy value, Payroll execution, Accounting posting, Price Book action, Preview mutation, Production access, dashboard, or autonomous recommendation.
- SOURCE.4 population is not treated as a prerequisite for validating the consumer contract. Its population remains `SOURCE_PARTIAL` until Migration supplies current admitted evidence.

## Mechanical result

`ECO_LAUNCH_EVIDENCE_VALIDATED`

The existing facts-to-policy boundary is preserved. Scheduled, worked, Jobsite,
paid, productive, and unclassified-paid time remain separate measures. A missing
Job measure now propagates as missing through Employee and Company aggregation;
it cannot be converted to zero or a partial total. Employee scheduled time is
aggregated only from explicit Employee/Job/Appointment schedule relationships.

The new `eco.launch-evidence-readiness.v1` packet is a bounded validator over the
existing labor and accepted Economics contracts. It does not acquire or promote
source data. It emits deterministic domain states, smallest blockers, source
authorities, evidence identities, labor-attribution classes, Payroll prerequisites,
SOURCE.4-independent population state, policy gates, and an immutable digest.

## Time and labor authority

| Evidence | Authority and identity | Effective time | Correction behavior | Employee / Job / Branch | Readiness |
|---|---|---|---|---|---|
| Scheduled Appointment | Scheduling Appointment plus Dispatch assignment | scheduled start/end | owning-domain version/lifecycle | Employee/Job/Appointment/Branch relationship required | `AVAILABLE` contract; never worked time |
| Workday Clock In/Out and office Timecard | Timekeeping `ApprovedWorkdayTimeFact`, entry/revision/approval and punch event IDs | work date, interval, approved-at | immutable successor revision and correction lineage | Employee and optional Branch; no Job identity | `AVAILABLE` contract |
| Job-specific clock interval | Timekeeping `JobWorkedInterval`, interval/revision and source event IDs | start/stop | original preserved; corrected successor with reason and audit lineage | Employee/Job; Appointment and Branch where admitted | `AVAILABLE` contract |
| Jobsite hours | Dispatch/field-service admitted interval | admitted arrival/location interval | source successor semantics required | Employee/Job/Appointment/Branch required | `PARTIAL`; no route or arrival inference |
| Paid time | approved Workday Time / Payroll Time Input snapshot | approved work date and pay period | digest-bound approved revisions | Employee-level; Job assignment prohibited | `AVAILABLE` contract |
| Productive time | explicitly classified accepted operational interval | source interval | source revision must remain in provenance | Employee/Job/Appointment/Branch required | `PARTIAL` / `SOURCE_REQUIRED`; no KPI policy selected |
| Payroll period | Timekeeping pay-period identity and approved snapshot; Payroll reporting period | period start/end and processing identity | active/superseded source state retained | Company/Employee; not implicitly Job-scoped | `AVAILABLE` contract, population unproven |

Job labor classification is exactly one of `JOB_ATTRIBUTABLE`,
`PAID_UNALLOCATED`, `SCHEDULED_ONLY`, `MISSING`, or `CONFLICTING`.
`JOB_ATTRIBUTABLE` requires actual Employee/Job worked evidence. Generic paid time
never gains Job identity. Multi-technician Jobs remain one evidence row per
Employee/Job/Appointment relationship.

## Launch readiness matrix

This is contract/readiness validation, not a claim that current Preview contains a
complete live population.

| Domain | State | Smallest exact blocker to live complete consumption |
|---|---|---|
| Revenue | `PARTIAL` | accepted earned-value evidence for the requested Job/period is not proven in an authenticated current Preview population |
| Settlement | `PARTIAL` | accepted settlement identity/basis and applicable recognition authority are not proven; Payment remains a distinct assertion |
| Direct Labor | `PARTIAL` | accepted worked-time attribution and approved monetary labor allocation must both exist for the same scope |
| Payroll | `PARTIAL` | current population proof is absent for compensation effective date, rate, accepted paid time, overtime applicability, period, revision state, jurisdiction/tax tables, and relevant elections |
| Direct Material | `PARTIAL` | accepted actual Job issue/use quantity and costing authority are not proven; purchasing or selling price cannot substitute |
| Other Direct Cost | `PARTIAL` | an accepted attributable cost fact is required for each implemented fleet, subcontractor, or merchant-cost component |
| Overhead | `PARTIAL` | `OVERHEAD_ALLOCATION_READINESS = NOT_READY` until approved pool and allocation-basis authority exist |
| Job Identity/Lifecycle | `PARTIAL` | current admitted SOURCE.4 Job/Appointment population is still Migration-owned |
| Service Line / Category | `PARTIAL` | canonical accepted Job classification is not proven for the current population |
| Accounting | `PARTIAL` | current accepted Accounting reconciliation is not proven; QBO source-reported or historical evidence is not Accounting truth |

For an evaluated packet, absent inputs emit `ABSENT`, incompatible admitted values
for the same reconciliation key emit `CONFLICTING`, and fully accepted evidence
emits `AVAILABLE`. `NOT_APPLICABLE` is reserved for an explicitly inapplicable
prerequisite; it is never inferred from absence.

## Revenue, settlement, material, and cost controls

- Earned operational value, Invoice, Payment assertion, settlement, cash, and
  Accounting recognition retain separate components, identities, bases, and as-of
  timestamps in the existing measurement contracts.
- HCP and QBO evidence with the same component and reconciliation key is compared by
  immutable value digest. Different values produce `CONFLICTING`; neither source is
  selected and no sum is emitted. QBO source-reported evidence is structurally
  prohibited from `accepted_for_measurement=True`.
- Direct material requires accepted actual cost evidence. Planned Price Book material,
  purchase/receipt alone, or selling price does not satisfy Job material cost.
- Missing direct labor, material, other direct cost, or overhead is never zero.
- Payroll admission requires authoritative complete reporting plus separately approved
  Company-scoped labor attribution; the launch packet additionally makes each upstream
  Payroll prerequisite visible. No burden rate is supplied.

## Preview observation

Read-only probes on 2026-09-12 showed Preview healthy with database and Redis
connected at deployed version `b5dff4b0203fe9a725a0ff844279876f410cba12`.
The public platform contract returned HTTP 200. Both Economics workspace and
measurement-foundation endpoints correctly returned HTTP 401 without an approved
identity. No credentials were sought, no authenticated totals were read, and no
Preview data was mutated. Preview is behind this branch and behind current protected
authority, so live population states remain `SOURCE_PARTIAL`, not `SOURCE_CURRENT`.

## Qualification

- Focused evidence tests: 17 passed.
- Affected Economics, operational measurement, Timekeeping, Payroll, Inventory,
  Purchasing, and QBO tests on fresh PostgreSQL: 667 passed; one unrelated Purchasing
  concurrency assertion failed once and passed on immediate isolated rerun.
- Ruff: changed files pass. Repository-wide Ruff reports 135 pre-existing findings in
  unrelated files.
- MyPy: changed source files pass.
- Python compile: application and tests pass.
- Alembic fresh zero-to-head: passed, single head `d4f6h8j0l2n4`.
- Alembic current=head: passed.
- Alembic drift check: no new upgrade operations detected.
- `git diff --check`: passed.

## Remaining policy and source gates

- Policy gates: labor burden, break-even method, productive-hour definition, revenue
  recognition where applicable, and overhead pool/allocation method.
- Source gates: current admitted SOURCE.4 operational population; authenticated
  current Preview evidence; accepted Jobsite/route evidence; accepted compensation,
  Payroll prerequisites and labor allocation; actual Job material issue/costing;
  attributable other direct costs; accepted QBO/Accounting reconciliation.
- No All County value, missing-input default, profitability output, repricing decision,
  employment conclusion, or autonomous action was added.

Enterprise owns protected integration and any later authenticated Preview validation.
Production remains untouched.

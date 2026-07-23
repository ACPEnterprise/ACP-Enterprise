# Dispatch Workspace Foundation

## Purpose and boundary

Dispatch is a protected, read-oriented frontend workspace at `/dispatch`. It composes authoritative Scheduling and Jobs query results for daily operational awareness. It does not own Appointment timing, Job lifecycle, workforce identity, assignment, routing, capacity, or location state.

The flow remains:

```text
Application Shell
  -> Dispatch route
  -> Dispatch presentation components
  -> Scheduling and Jobs React Query hooks
  -> existing typed API clients
  -> domain-owned HTTP APIs
```

There is no Dispatch API, persistence model, mutation service, event, query-key family, or copied server-state store in this milestone.

## Scope controls

The workspace defaults to the browser-local current date because the authenticated Company snapshot does not currently include an authoritative Company timezone. It converts the selected local calendar day into a half-open UTC range `[start_at, end_at)` for the Scheduling API. Previous-day, Today, next-day, and native date controls use the same calculation, including month and year rollover.

Branch options come exclusively from the authenticated active Company's accessible Branch snapshot. The selected Branch is passed to both domain APIs as a server-side filter; browser filtering is never a tenant-security boundary. All accessible Branches is the default.

## Appointment queue

Scheduling owns the bounded Appointment query and its query keys. The queue preserves the Scheduling API's arrival ordering and displays Appointment number, lifecycle state, arrival window, and expected duration. Business numbers navigate to protected Appointment detail.

Scheduling list projections do not embed Jobs-owned relationship information. The queue deliberately does not issue an N+1 Job lookup or infer a relationship. Appointment detail resolves the authoritative relationship through the Jobs `appointment_id` filter and provides Job navigation.

## Operational Jobs queue

Jobs owns the query and keys. Dispatch requests the nonterminal presentation set `draft`, `ready`, `in_progress`, and `paused`, scoped by Branch and ordered by the backend's controlled priority ranking in descending order. The queue shows Job number, Customer display, Service Location label, priority, and current status. This grouping is presentation only and does not duplicate transition rules or imply assignment state.

## Summary and error isolation

Appointment and Job totals use server metadata. Paused and high-priority counts are explicitly labeled as visible-page counts. Each queue has independent loading, empty, error, and retry behavior, so one unavailable permission or service does not destroy the other section. Known non-transient HTTP statuses use the shared no-retry policy; transient failures use bounded retries.

## Permissions and workforce dependency

Scheduling results require `COMPANY_SCHEDULING_READ`; Jobs results require `COMPANY_JOB_READ`. The frontend authentication snapshot does not contain resolved permission codes, so `/dispatch` is protected by authentication while each backend section remains the authorization authority. A user with only one domain permission receives a safe, section-specific denial for the other.

Employee persistence currently exposes Company, home Branch, status, type, and display fields, but there is no reviewed Company/Branch-scoped workforce query service or HTTP contract. The model does not establish technician classification, availability, or assignment. Consequently this milestone includes no workforce panel and does not label Users or Employees as technicians. A future workforce-owned immutable projection can fill that layout seam without changing Scheduling or Jobs ownership.

`DispatchWorkspaceLayout` has an optional workforce composition boundary that renders
nothing today. A future workforce-owned panel can occupy that boundary after an
authoritative contract is approved; Appointment and Job queues will not need to be
redesigned or made responsible for workforce data.

## Technician capability and recommendation readiness

The current Employee model does **not** authoritatively represent technician
classification, skills, certifications, service competencies, equipment or vehicle
capabilities, geographic coverage, schedule availability, current workload, Branch
eligibility beyond a nullable home-Branch reference, or safety/work restrictions.
Role names, Job history, titles, and free-form text must not be used to manufacture
these facts.

A future Technician Capability Profile should be owned by an approved workforce or
field-operations bounded context and exposed through immutable Company- and
Branch-scoped projections. A reviewed recommendation service may then consider:

- required Job skills and complexity;
- technician proficiency and certifications;
- Branch eligibility and geographic coverage;
- current workload and schedule availability;
- equipment and vehicle capability;
- historical completion performance and callback rate;
- customer satisfaction and, where operationally appropriate, sales performance;
- Job priority.

Recommendation output must be explainable: each candidate should include the
authoritative eligibility facts, positive match factors, constraints, and material
tradeoffs that produced the ranking. A recommendation is advisory and must never
replace backend permission checks, licensing and certification requirements, safety
rules, work restrictions, Branch scope, availability validation, or the future
durable-assignment transaction. No scoring, suggested assignment, or automatic
assignment exists in this milestone.

## Deferred capabilities

Technician assignment, drag-and-drop dispatch, route optimization, maps, GPS, travel time, capacity optimization, technician mobile workflows, time tracking, Estimates, Invoices, Inventory, payroll, accounting, and Job costing remain deferred bounded-context integrations. None are simulated in the workspace.

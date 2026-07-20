# Version 1.0: 30-Day Release Plan

## Objective

At the end of 30 days, All County Plumbing & Leak can execute the agreed launch workflow in ACP Enterprise—from customer intake through dispatched work and recorded revenue—with a controlled production rollout and a credible path to Housecall Pro retirement.

This is an aggressive launch plan. Scope must be limited to the workflows required for operational replacement. Each week ends with demonstrated, integrated software rather than disconnected components.

## Release guardrails

- QuickBooks remains the accounting system of record.
- Multi-company SaaS administration is out of scope, but tenant and branch boundaries must be enforced in the design.
- Prefer complete primary workflows over broad configuration and edge-feature parity.
- No launch occurs without migrated-data reconciliation, role validation, backup/restore evidence, operational monitoring, and an approved rollback procedure.
- Any Housecall Pro capability identified as launch-critical must have an owner, acceptance criteria, and cutover disposition: implement, integrate, migrate, retain temporarily, or explicitly retire.

## Week 1 — Foundation (Days 1–7)

**Outcome:** A secure, deployable platform foundation supports real domain development.

### Deliverables

- Confirm the Housecall Pro workflow inventory, launch users, branches, integrations, reports, and data-migration scope.
- Establish production and non-production environments, CI gates, artifact builds, configuration, secrets, and release ownership.
- Implement authenticated users, roles, permissions, company and branch context, and tenant-scoped request handling.
- Establish module boundaries, standard API errors, structured logging, request/correlation IDs, audit behavior, and liveness/readiness checks.
- Implement the transactional outbox and documented event envelope.
- Establish migration, backup, restore, monitoring, alerting, and incident procedures.
- Produce initial customer, service-location, job, appointment, estimate, invoice, and payment data mappings from Housecall Pro and QuickBooks boundaries.
- Create the version 1.0 end-to-end test skeleton and synthetic launch dataset.

### Exit criteria

- A user can authenticate and is restricted to the correct role, company, and branch.
- A reference transaction commits authoritative state and an outbox event atomically.
- CI deploys a production-like environment from a clean checkout.
- An empty database and a production-like database migrate successfully.
- Stakeholders approve the launch-critical workflow and data inventory.

## Week 2 — CRM and Operations (Days 8–14)

**Outcome:** Office staff can manage the customer-to-dispatch workflow.

### Deliverables

- Implement customer, contact, and service-location records, search, deduplication rules, notes, and history.
- Implement lead/service-request intake and required communication attribution.
- Implement jobs/work orders, appointments, schedule views, assignment, rescheduling, cancellation, and status rules.
- Implement the dispatch board, technician availability, en-route/arrival status, and operational exception handling.
- Implement essential technician mobile/responsive views for itinerary and job context.
- Emit and consume versioned CRM, appointment, dispatch, and job events.
- Run the first representative data import and reconcile counts, required fields, relationships, duplicates, and rejected rows.
- Demonstrate the integrated intake-to-arrival workflow to dispatchers and field representatives.

### Exit criteria

- Authorized staff can create/find a customer, book work, assign a technician, and track arrival without direct database intervention.
- Role and branch restrictions pass API and end-to-end tests.
- Imported records meet documented reconciliation thresholds with every exception classified.
- Dispatch and field users approve the primary workflow or record blocking gaps with owners.

## Week 3 — Revenue (Days 15–21)

**Outcome:** The platform supports the commercial path from estimate to recorded payment while preserving the QuickBooks boundary.

### Deliverables

- Implement the launch pricebook, estimate creation/options, discounts, approvals, and customer authorization evidence.
- Implement technician work notes, photos/forms required for closeout, material capture where launch-critical, and job completion.
- Implement operational invoices, payment requests/collection or payment recording, refunds/adjustments required at launch, and receipts.
- Implement reliable QuickBooks export/integration and explicit reconciliation ownership.
- Implement customer notifications required for appointment, dispatch, estimate, invoice, and receipt workflows.
- Replace dashboard hard-coded values with tenant-scoped projections for launch KPIs and exceptions.
- Validate idempotency, financial calculations, event delivery, retries, and failure recovery.
- Execute full journey rehearsals with office, field, management, and finance representatives.

### Exit criteria

- A representative job moves from booked appointment through approved estimate, completed work, invoice, payment, receipt, and accounting handoff.
- Money totals reconcile across source records, events, customer views, analytics, and QuickBooks handoff.
- Payment retries cannot create duplicate charges or records.
- Critical end-to-end and reconciliation suites pass.

## Week 4 — Production rollout (Days 22–28)

**Outcome:** Production is proven through controlled use, migration rehearsal, and operational acceptance.

### Deliverables

- Freeze launch scope; triage defects by safety, data integrity, revenue, workflow continuity, and usability.
- Conduct security, privacy, performance, accessibility, migration, backup/restore, and disaster-recovery verification.
- Complete at least one timed dress rehearsal of export, transform, import, reconciliation, smoke testing, rollback decision, and recovery.
- Train office, dispatch, technician, management, finance, and support users against role-specific workflows.
- Run a limited pilot with selected users or work while Housecall Pro remains available under the approved coexistence rules.
- Monitor workflow completion, error rate, support demand, event/outbox lag, data reconciliation, and external integrations.
- Resolve launch blockers and obtain product, engineering, operations, finance, and executive go/no-go decisions.

### Exit criteria

- The [launch checklist](launch-checklist.md) has no unresolved blocking item.
- Pilot transactions reconcile and users can complete critical workflows within acceptable operating times.
- On-call, support, escalation, communications, rollback, and vendor contacts are confirmed.
- The final migration package and immutable release artifacts are approved.

## Days 29–30 — Cutover and stabilization

### Day 29: Cutover

- Confirm final go/no-go and change freeze.
- Execute the approved Housecall Pro extraction and write restrictions.
- Import and reconcile launch data.
- Deploy the approved release and run role-based production smoke tests.
- Start command-center monitoring and record every exception in the launch log.
- Roll back only according to the defined decision thresholds and authority.

### Day 30: Stabilization

- Reconcile customers, open work, schedule, estimates, invoices, payments, and integration delivery.
- Review support issues and operational metrics at agreed intervals.
- Fix only approved launch-critical defects through the controlled release path.
- Record residual Housecall Pro dependencies and owners.
- Decide whether to complete retirement, extend controlled coexistence, or invoke rollback.

## Success measures

- All launch-critical workflows can be completed in ACP Enterprise by their intended roles.
- No confirmed cross-tenant/branch access, unreconciled payment duplication, or material data loss occurs.
- Imported launch records meet approved reconciliation thresholds.
- Availability, latency, and workflow error rates remain within launch targets.
- Every fallback to Housecall Pro is recorded and classified.
- Operations and finance sign off on workflow continuity and data accuracy.

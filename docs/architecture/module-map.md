# Module Map

ACP Enterprise is organized as a modular monolith: one deployable backend with business modules that own their data and behavior. Modules communicate synchronously through defined application interfaces and asynchronously through durable business events. Direct writes to another module's tables are prohibited.

## Modules

### Foundation

Provides configuration, database sessions, migrations, identifiers, time handling, health checks, event infrastructure, shared API mechanics, and observability. Foundation contains technical primitives only; it must not become a home for unowned business logic.

**Depends on:** PostgreSQL and platform infrastructure.
**Used by:** every module.

### CRM

Owns customers, contacts, leads, service locations, customer preferences, tags, and relationship history. It provides the authoritative customer and location identities used by downstream workflows.

**Depends on:** Foundation, Communications.
**Primary consumers:** Operations, Sales, Financial, Analytics, Automation.

### Operations

Owns service requests, jobs/work orders, appointments, job lifecycle, assignments, status transitions, notes, attachments, and operational exceptions. It coordinates the end-to-end execution of customer work without owning customer, pricebook, or accounting facts.

**Depends on:** Foundation, CRM, Sales.
**Primary consumers:** Dispatch, Field Service, Financial, Inventory, Analytics, Automation.

### Dispatch

Owns dispatch-board views, technician availability, assignment decisions, route and capacity constraints, and dispatch exceptions. Operational appointments remain the source of truth; Dispatch provides planning and execution decisions around them.

**Depends on:** Foundation, Operations, Field Service, CRM.
**Primary consumers:** Operations, Communications, Analytics, Automation.

### Field Service

Provides the technician-facing experience: daily itinerary, en-route and arrival status, work execution, forms, photos, notes, materials, customer approvals, and completion evidence. It uses Operations workflows and emits field activity without duplicating job ownership.

**Depends on:** Foundation, Operations, CRM, Sales, Inventory, Communications.
**Primary consumers:** Dispatch, Financial, Analytics, Automation.

### Sales

Owns the pricebook, estimates, estimate options, discounts, approvals, sales attribution, and conversion lifecycle. Approved estimates provide the commercial scope used by jobs and invoices.

**Depends on:** Foundation, CRM.
**Primary consumers:** Operations, Field Service, Financial, Inventory, Analytics.

### Financial

For version 1.0, owns operational invoices, payment requests, payment records, refunds, tax calculations, and reconciliation with the external accounting system. General ledger, accounts payable, payroll, and full accounting controls remain outside version 1.0.

**Depends on:** Foundation, CRM, Operations, Sales.
**Primary consumers:** Communications, Analytics, Automation; later external accounting integrations.

### Inventory

Owns physical stock-item identity, warehouse and vehicle quantities, locations,
movements, reservations, transfers, adjustments, reorder thresholds, and valuation
evidence. Operations owns Jobs, and Jobs are authoritative for material requirements
and actual consumption attribution. Field Service is the technician-facing recording
experience and never duplicates Job ownership. Initial releases may capture Job
materials without complete stock management. See the
[Inventory Domain Architecture Brief](inventory/domain-architecture-brief.md).

**Depends on:** Foundation, Platform, Operations contracts.
**Primary consumers:** Field Service, Purchasing, Financial, Analytics, Automation.

### Purchasing

Owns operational Vendor identity, purchase orders, receipts, discrepancies, and
procurement lifecycle. It requests Inventory movements through owned contracts and
provides evidence for accounting handoff; it does not own stock, accounts payable,
ledger behavior, or QuickBooks records. See the
[Purchasing Domain Architecture Brief](purchasing/domain-architecture-brief.md).

**Depends on:** Foundation, Platform, Inventory contracts, Operations demand references.
**Primary consumers:** Inventory, Financial, Analytics, Automation.

### Communications

Owns communication threads, messages, delivery attempts, templates, consent, and provider integration for phone, SMS, and email. Customer identity remains in CRM; communication delivery records remain here.

**Depends on:** Foundation, CRM for addressed customer communications.
**Primary consumers:** CRM, Operations, Dispatch, Sales, Financial, Automation.

### Analytics

Owns read-optimized projections, KPI definitions, dashboards, exports, and operational reporting. Analytics consumes authoritative data and events but does not become the system of record for business workflows.

Luminary is the Business Economics and Profitability Intelligence layer within
this analytics boundary. It is not a separate AI persona. Luminary consumes
authoritative operational and reconciled financial facts, exposes provenance
and missing-data state, and never writes operational or accounting records.

**Depends on:** Foundation and events from all business modules.
**Primary consumers:** staff, managers, owners, Automation.

### Automation

Owns triggers, conditions, scheduled rules, approvals, actions, retry policy, and automation audit history. Automations invoke authorized module APIs; they do not write module tables directly.

**Depends on:** Foundation, Platform identity and policy, module APIs, and business events.
**Primary consumers:** all operational modules.

### Platform

Owns identity, authentication, authorization, company and branch structure, tenant context, feature configuration, audit access, integration credentials, and—when SaaS begins—tenant provisioning, plans, and platform billing.

**Depends on:** Foundation.
**Used by:** every protected module.

## Dependency view

```text
Foundation ───────────────────────────────────────────────► all modules
    │
    └── Platform (identity, tenant, policy) ──────────────► protected modules

CRM ──────► Sales ──────► Operations ──────► Dispatch
 │             │              │                  │
 │             └──────────────┼──────► Financial│
 │                            ├──────► Field Service ◄──── Inventory
 └────► Communications ◄──────┴──────────────────┘

Operations ── material demand/use ──► Inventory ── reorder signal ──► Purchasing
Purchasing ── receipt movement request ──► Inventory
Inventory + Purchasing ── controlled evidence ──► Accounting / QuickBooks handoff

Business-module events ──────► Analytics
Business-module events ──────► Automation ──────► authorized module APIs
```

Arrows indicate a dependency or consumption relationship, not table access. Cycles visible at the business-workflow level must be implemented through stable interfaces or events rather than circular source-code dependencies.

## Current implementation status

The repository currently implements Foundation and Platform elements, a
business-event journal, Customer workflows, substantial Jobs and Scheduling
workflows, early Analytics and Beacon intelligence, a Mission Control frontend,
Development Factory and engineering-control foundations, Workforce Capability
persistence, and controlled migration foundations. Dispatch is currently a
frontend projection over Jobs and Scheduling rather than an assignment domain.
The PRICEBOOK.1 foundation is implemented across backend and frontend behavior,
including permissions, price-version activation, immutable commercial snapshots,
and audit evidence. Planned enhancements include Inventory-item mappings,
component units of measure, and later downstream commercial integrations; those
extensions are not part of the current PRICEBOOK.1 contract. Estimates, Invoicing,
Payments, Inventory, Purchasing, Communications delivery, Field Service, and
Accounting remain incomplete, architecture-only, or foundation-only according to
their specific contracts. A persistence table or migration path alone is not a
claim of operational product completion.

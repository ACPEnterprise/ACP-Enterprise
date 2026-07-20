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

Owns catalogued stock items, warehouse and vehicle quantities, reservations, transfers, adjustments, reorder thresholds, and job material consumption. Initial releases may implement a deliberately narrow material-tracking scope.

**Depends on:** Foundation, Sales, Operations.
**Primary consumers:** Field Service, Financial, Analytics, Automation.

### Communications

Owns communication threads, messages, delivery attempts, templates, consent, and provider integration for phone, SMS, and email. Customer identity remains in CRM; communication delivery records remain here.

**Depends on:** Foundation, CRM for addressed customer communications.
**Primary consumers:** CRM, Operations, Dispatch, Sales, Financial, Automation.

### Analytics

Owns read-optimized projections, KPI definitions, dashboards, exports, and operational reporting. Analytics consumes authoritative data and events but does not become the system of record for business workflows.

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

Business-module events ──────► Analytics
Business-module events ──────► Automation ──────► authorized module APIs
```

Arrows indicate a dependency or consumption relationship, not table access. Cycles visible at the business-workflow level must be implemented through stable interfaces or events rather than circular source-code dependencies.

## Current implementation status

The repository currently implements Foundation elements, a business-event journal, health endpoints, early Analytics endpoints, and a Mission Control frontend. Other modules are target boundaries, not claims of completed functionality. Product specifications should be added under `docs/product/modules/` before each module is implemented.

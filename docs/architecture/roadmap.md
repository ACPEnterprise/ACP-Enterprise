# Platform Roadmap

The roadmap communicates intended sequencing, not a promise to build every listed capability unchanged. Release scope is controlled by validated operational needs, explicit acceptance criteria, and launch readiness.

## Version 1.0 — Housecall Pro replacement

**Outcome:** All County Plumbing & Leak can operate its normal customer-service and field-service workflows without Housecall Pro.

Required capabilities:

- Identity, roles, company and branch context, and auditability
- Customer, contact, lead, and service-location records
- Service requests, jobs, appointments, scheduling, and dispatch
- Technician workflow for status, notes, photos, forms, and completion
- Pricebook, estimates, customer approval, invoices, and payment collection
- Customer notifications and essential communication history
- Operational dashboard and launch-critical reports
- Controlled data migration, reconciliation, backup, monitoring, support, and rollback procedures
- Necessary integrations for payment processing, messaging, and mapping
- The separately gated internal-accounting critical path defined by
  [ADR 0005](adr/0005-internal-accounting-system-of-record.md)

QuickBooks remains authoritative only until the independently accepted internal-
accounting cutover. Nonessential SaaS administration, broad AI capabilities, and
speculative workflow variants remain out of scope.

## Version 1.5 — Operational depth and revenue optimization

**Outcome:** The platform is more efficient and measurable than the replaced system.

Candidate capabilities:

- Improved dispatch capacity and route planning
- Memberships and recurring-service workflows
- Advanced pricebook, estimate options, financing, and sales coaching
- Inventory tracking and replenishment
- Configurable communications and workflow automation
- Technician, campaign, call, conversion, and profitability analytics
- Broader mobile resilience and offline-tolerant field workflows
- Hardened integration and data-quality operations

## Internal Accounting cutover program

**Outcome:** ACP Enterprise replaces QuickBooks as the operational accounting
system without weakening financial control.

Expected areas:

- Chart of accounts and double-entry general ledger
- Accounts receivable and accounts payable
- Bank and payment reconciliation
- Vendor, purchasing, expense, tax, and close workflows
- Financial statements, period controls, immutable audit trails, and accountant access
- Parallel-run reconciliation and independently approved cutover criteria

The controlling decision and Day-1 boundary are recorded in
[ADR 0005](adr/0005-internal-accounting-system-of-record.md). QuickBooks becomes
read-only only after independent financial verification and owner-authorized
cutover.

## Version 3.0 — Multi-company SaaS platform

**Outcome:** Proven capabilities can be securely operated by multiple independent home-service companies.

Expected areas:

- Enforced tenant isolation and tenant-specific configuration
- Automated onboarding, provisioning, migration, plans, and SaaS billing
- Per-tenant branding, workflows, pricebooks, integrations, and retention policies
- Fleet-level operations, regional controls, support tooling, and delegated administration
- SaaS reliability objectives, compliance program, data portability, and tenant lifecycle management
- Scalable analytics and automation isolation

Tenant-aware boundaries should be designed early, but version 3.0 product administration should not delay the single-company version 1.0 launch.

## Long-term vision

ACP Enterprise becomes an intelligent operating system for home-service businesses: a unified platform that manages demand, people, work, materials, customer experience, and money. Trustworthy operational history enables forecasting, proactive exception detection, recommended actions, and controlled automation. Humans remain accountable for consequential customer, workforce, and financial decisions.

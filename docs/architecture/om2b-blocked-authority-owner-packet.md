# OM2-B blocked-authority owner decision packet

Authority inspected initially at `824ff2cec5c611a14a6b4f9696430e47758a2c08` and
reconciled through `be7f6796c1ca74a6252f2aa5658ee70f1806f079` on 2026-08-30.

This packet is decision preparation, not authority. It creates no roles, domain records,
permissions, migrations, provider actions, or Production configuration. Existing CRM and
Workforce program branches remain active-owned and untouched.

## 1. CSR role

ACP has no canonical CSR role. Its launch matrix currently defines Company Administrator,
Office Manager, Dispatcher, Technician, Auditor, and Support. The least-privilege default is
a new branch-scoped `CSR` role after owner acceptance.

| Area | Recommended | Prohibited by default | Owner option |
|---|---|---|---|
| Customers, Contacts, Locations | `COMPANY_CUSTOMER_READ`, `COMPANY_CUSTOMER_MANAGE` | archive/consolidation unless separately authorized | Split archive/consolidation when CRM authority adds granular permissions |
| Estimates | READ + MANAGE | no unrelated Price Book activation | Remove MANAGE for inquiry-only CSR |
| Scheduling | READ | MANAGE | Add MANAGE only if CSRs schedule/reschedule |
| Jobs | READ | MANAGE, EXECUTE | Add MANAGE only for accepted office lifecycle actions |
| Dispatch | READ | MANAGE | Remove READ if dispatch state is unnecessary |
| Invoices and payments | INVOICE_READ + PAYMENT_READ | issue, adjust, apply, collect, refund, reconcile, finance approve | Remove PAYMENT_READ if even status is finance-restricted |
| Communications | READ | MANAGE/provider administration | Add a future narrow customer-communication action permission, not broad MANAGE |
| Inventory | optional READ only | all mutations | Include READ only if materials status is part of customer service |
| Purchasing | none | all | none |
| Payroll, Accounting, AP, Economics | none | all | none |
| Administration, Migration | none | all | none |
| Beacon | none | REVIEW/OWN/ASSIGN | REVIEW only in a separately accepted service-alert workflow |

Decision `ROLE-CSR-1`: choose **service CSR** (recommended matrix above), **inquiry CSR**
(remove Customer/Estimate MANAGE), or **scheduler CSR** (add Scheduling MANAGE). Branch grants
remain mandatory. Direct API authorization, not UI visibility, is authoritative.

Implementation: add one launch-role definition and catalog tests; no schema change. Acceptance
must prove cross-Company and ungranted-Branch denial, all prohibited financial/admin actions,
and UI/API agreement.

## 2. Restricted Employee role

The current Technician role contains tenant-wide Customer, Scheduling, and Job reads and is not
a safe substitute for an own-data physical-device persona. Recommended `RESTRICTED_EMPLOYEE`:

- `COMPANY_TIMEKEEPING_OWN_PUNCH`, `COMPANY_TIMEKEEPING_OWN_READ`;
- `COMPANY_PAYROLL_STATEMENT_OWN_READ`;
- no standing Customer, Scheduling, Dispatch, Inventory, Purchasing, Accounting, Migration,
  Beacon, or Administration permission;
- assignment/field visibility only through an accepted own-assignment projection that resolves
  authenticated Membership -> Employee server-side; never from a caller-supplied employee ID.

Decision `ROLE-EMP-1`: **own-data role** (recommended), **Technician-derived role** (adds Job
READ/EXECUTE and Scheduling READ after assigned-resource scoping is proven), or **time/pay-only
role**. This decision must not grant Payroll administration. No schema change is expected.

Physical-device qualification must attempt another employee's pay statement, punches, assignment,
and employee ID; cross-Branch and cross-Company references; deactivation; role removal/regrant;
and access-token refresh after authorization-version change.

## 3. Fleet / Asset authority

The bank contains `BANK.ASSET.001` through `.010`; Fleet identity is `.005` and depends on the
customer-equipment/install-base chain. No native Fleet authority may be skipped into existence.

Recommended architecture after the bank releases it:

- `AssetTypeVersion`: immutable type/configuration version, Company scoped.
- `Asset`: stable Company identity, optional Branch custody, type version, serial/VIN-like values
  as evidence rather than globally trusted identity, lifecycle/version.
- append-only `AssetAssignment`, `AssetOperationalState`, `AssetInspectionEvidence`,
  `AssetMaintenanceEvidence`, and `AssetDocumentBinding`.
- references, not duplicated truth, to Inventory location, Employee/crew, Job, Appointment, and
  Dispatch assignment. Inventory remains quantity authority and Dispatch remains work authority.
- optimistic concurrency, tenant-scoped idempotency, immutable audit/Business Events, archive not
  deletion.

Permissions should be separate: ASSET_READ, ASSET_MANAGE, ASSET_ASSIGN, ASSET_INSPECT,
ASSET_MAINTENANCE_RECORD, ASSET_DOCUMENT_READ/MANAGE, ASSET_REPORT_READ, ASSET_ADMIN. No one
permission should imply Inventory movement or Dispatch mutation.

Decision `ASSET-1`: approve the dependency order and append-only evidence model. Real asset types,
inspection requirements, maintenance intervals, readiness rules, and document retention remain
versioned `UNCONFIGURED` policy. Expected schema is additive and begins only at `.001`; acceptance
uses synthetic vehicles/assets and proves tenant/Branch isolation and history preservation.

## 4. In-product notification authority

`notification_outbox` is durable external-delivery intent/evidence. It is not a user inbox.
Recommended separate `UserNotification` authority:

- Company + recipient Membership/User + notification type + source identity form idempotency;
- safe title/summary and typed internal destination, never raw outbox payload or provider error;
- created, read, archived/dismissed lifecycle with actor and timestamps;
- resource permission is rechecked on list and deep-link navigation; key possession grants nothing;
- mobile/web use the same recipient projection; retention class is configurable and deletion never
  removes source-domain or delivery evidence.

Options: **event-derived inbox** (recommended), explicit domain commands, or hybrid. Event-derived
minimizes dual writes; explicit commands are appropriate only when no authoritative event exists.
Implementation requires additive inbox tables/API/UI and separate permissions `NOTIFICATION_READ`
and `NOTIFICATION_MANAGE_OWN`; administrative delivery permissions remain Communications-owned.

Decision `NOTIFY-1`: approve derivation model and whether user dismissal is archive-only or a
separate reversible state. Qualify duplicate event replay, cross-tenant probing, permission loss,
safe deep links, and outbox failure independence. No real delivery.

## 5. Universal Task / Action Center

Recommendation: **composition-only Action Center now, hybrid later**. Domain queues keep their
state and disposition APIs. A generic task is justified only for a genuinely cross-domain human
obligation with independent assignee, due/configuration state, and lifecycle; it must reference,
not replace, its source.

Options are generic Task aggregate (high duplicate-workflow risk), composition-only (lowest risk),
or hybrid (recommended long-term). Beacon remains signal/intelligence, not task authority.

Decision `ACTION-1`: approve composition-only first and require a later explicit task-use-case
before adding persistence. Initial implementation has no migration: federated read projection,
source status, permission-filtered deep link, and counts whose partial results are explicit.
Qualification proves no cross-domain mutation, no unauthorized result-existence leakage, stable
pagination, and source-state freshness.

## 6. Document Center authorization

Use a federated document catalog with domain authorization adapters. Every adapter resolves
Company, Branch/own-data scope, resource state, and the exact domain read permission before a row
or count is returned. There is no universal document-read permission.

- Estimate: ESTIMATE_READ plus Customer/Company binding.
- Invoice/receipt: INVOICE_READ/PAYMENT_READ and domain binding.
- Pay Statement: `STATEMENT_OWN_READ` for self; separate Payroll admin authority for others.
- Purchasing: PURCHASE_READ plus document-specific source binding.
- Migration: accepted migration evidence permission; never source filesystem access.
- Service Agreement: future agreement permission adapter.

Opaque access grants, if approved, are short-lived/revocable and bind Company, resource, audience,
purpose, artifact digest, and expiration. They never expose storage paths.

Decision `DOC-1`: approve federated adapters (recommended) versus a central metadata index. The
first implementation can be read-only with no schema if adapters list existing artifacts; grants
require additive persistence. Test IDOR, own-data, revoked authority, archived resources, pagination,
and existence leakage.

## 7. Enterprise Search

| Option | Strength | Risk |
|---|---|---|
| Federated domain search | Reuses current authorization and fresh domain truth; low operational cost | Fan-out latency and heterogeneous ranking |
| Central permission-aware index | Fast unified ranking at scale | freshness/tombstone, ACL projection, leakage, operations burden |
| Hybrid | Federated authority with selected indexed discovery | greatest complexity; useful only after measured need |

Recommendation: federated first. Each domain adapter accepts Company, authorized Branch set,
query, bounded limit, and opaque cursor; it returns only authorized typed summaries. The aggregator
must not reveal hidden counts or time differences as useful existence oracles. Exact resource fetch
reauthorizes.

Decision `SEARCH-1`: approve federated first and the searchable domain set. No schema migration.
A later index requires explicit freshness SLA, authorization projection, tombstone/rebuild behavior,
and outage policy. Qualification covers cross-Company/Branch searches, permission removal, paging,
partial-domain failure, injection-like input, and load bounds.

## 8. CRM survivorship / consolidation (`BANK.CRM.001`)

Mechanically safe default: create a reversible consolidation group/link, choose no survivor until
authorized, preserve every source identity and historical reference, and never bulk-rewrite Jobs,
Estimates, Invoices, or Payments merely to hide a duplicate.

Always preserve: contacts, entered phone/email evidence and normalization, billing identities,
Service Locations, notes and visibility, Jobs, Estimates, Invoices, Payments, preference versions,
archive history, source identities, provenance, and audit/Business Events.

Owner-selectable survivorship:

- display/legal/customer name;
- primary contact, phone, email, billing identity;
- whether compatible Contacts/Locations are linked or copied;
- preference conflict handling (most restrictive is a safe display default but is not a legal-policy
  decision);
- active/archive state and which identity receives new work;
- whether downstream references remain linked-to-original (recommended) or are explicitly migrated.

Options: non-destructive relationship only (recommended first), canonical survivor with immutable
aliases, or destructive physical merge (not recommended). Decision `CRM-1`: select model and each
field-group rule; select who may propose/approve. Required permissions should split duplicate READ,
DISPOSITION, CONSOLIDATE_PROPOSE, and CONSOLIDATE_APPROVE from Customer MANAGE. Expected schema is
additive consolidation case/decision/provenance; no deletion. Synthetic acceptance covers conflicting
contacts/locations/preferences, open work, paid Invoice, archived record, reversal, concurrency, and
cross-tenant denial.

## 9. Workforce mutation authority (`BANK.WF.001`)

Existing read models/persistence already represent capability profiles, capability categories,
capabilities, certifications, equipment capability, working availability, and languages. The missing
decision is who can create/version/retire definitions and append Employee evidence.

Generic authority can be predetermined: Company-scoped versioned definitions; Employee-linked,
append-only effective-dated assignments/evidence; optimistic concurrency; explicit source/actor;
archive/retire rather than rewrite; deterministic readiness projections; separate catalog versus
Employee-evidence permissions.

Owner policy is required for proficiency classifications, required capabilities by service category,
credential verification authority and expiry consequences, working windows/overlap, emergency
availability, crew lead/size, and mandatory training. These may remain `UNCONFIGURED`.

Decision `WF-1`: approve generic mutation authority and approver separation. Recommended permissions:
WORKFORCE_READ, PROFILE_MANAGE, CAPABILITY_CATALOG_MANAGE, CREDENTIAL_RECORD, CREDENTIAL_VERIFY,
AVAILABILITY_MANAGE, CREW_MANAGE, TRAINING_RECORD, READINESS_READ, REPORT_READ. None imply Payroll,
Timekeeping correction, Dispatch assignment, or HR/compensation access. Migration is additive only
where current models lack history/version evidence. Qualification covers concurrency, expired evidence,
unconfigured policy, Branch crossover, Payroll leakage, audit, and Scheduling/Dispatch read composition.

## 10. Physical-iPhone Preview acceptance

Common setup uses synthetic Users, active Memberships, Employee links where relevant, explicit Branch
grants, canonical roles, Preview invitation/activation, and no shared credentials.

| Persona | Expected allow | Expected deny |
|---|---|---|
| Technician | assigned Job/field execution and accepted own Timekeeping if role includes it | admin, other employees, Payroll admin, Accounting, Purchasing approval |
| Dispatcher | Customer read, Scheduling/Dispatch, Job operations in granted Branch | Payroll, Accounting, admin, Employee own-pay data |
| CSR candidate | owner-selected CSR matrix | all prohibited matrix entries and ungranted Branch |
| Manager | Office Manager operations | Payroll/Accounting mutations unless separately granted |
| Admin | access/readiness administration and bounded owner-read | execution permissions not explicitly granted |
| Restricted Employee candidate | own identity, own accepted assignment/Timekeeping/pay statement | all other Employee/tenant/admin data |

Sequence: provision -> claim invitation -> authenticate -> verify visible/hidden navigation -> call
representative allowed and denied APIs directly -> try changed employee/company/branch identifiers ->
remove permission and Branch grant -> refresh/re-authenticate and verify denial -> deactivate Membership
-> verify denial -> restore and verify only restored authority. Record app/build SHA, API SHA, schema head,
persona fixture digest, authorization version, and results. Decisions `ROLE-CSR-1` and `ROLE-EMP-1`
must precede those two persona cases; the other four are mechanically startable.

## 11. Deduplicated Preview acceptance backlog

| Gate | Evidence to execute |
|---|---|
| Protected integration | Integrate qualified OM2-B branches through centralized protected workflow; verify expected heads and semantic file boundaries before merge |
| Integrated PostgreSQL | migration upgrade/current/single-head/drift; tenant/Branch adversarial queries; role change transactions; own-data pay/time/mobile attacks; CRM/Workforce DB suites after their decisions |
| Preview web | Customer/Field/CRM/Workforce/Owner Operations routes; authorization-driven navigation; empty/loading/forbidden/error states; desktop/tablet/phone accessibility |
| Preview services | `/health`, schema/release identity, configuration/external gates, audit/event pagination, notification-outbox regression; no real provider calls |
| Physical device | the six-persona sequence above, including revocation/re-authentication and cross-employee attacks |

Enterprise owns integration/deployment. Each run must bind current Git SHA, schema head, frontend build,
fixture digest, test version, and result; pending evidence must not be represented as passed.

## 12. Next-wave graph and decision order

```text
ROLE-EMP-1 -> restricted role + own-assignment contract -> physical iPhone acceptance
ROLE-CSR-1 -> CSR role -> Customer service and CRM acceptance
CRM-1      -> BANK.CRM.001 -> native duplicate review/consolidation UI
WF-1       -> BANK.WF.001  -> Workforce mutation/admin/readiness completion
NOTIFY-1   -> user inbox -> Notification Center + mobile notification projection
DOC-1      -> federated Document Center -> bounded customer/document access
SEARCH-1   -> Enterprise Search -> shared operator discovery
ACTION-1   -> composition Action Center -> cross-domain work queue
ASSET-1    -> BANK.ASSET.001..010 in order -> Fleet product
```

Recommended decision order: (1) Restricted Employee, because it unlocks physical-device acceptance;
(2) CSR, because it unlocks a canonical customer-service persona; (3) CRM survivorship, the highest
data-integrity decision; (4) Workforce mutation authority; (5) inbox; (6) Document Center; (7) Search;
(8) Action Center; (9) Fleet dependency/authority model. Fleet has broad product value but must not
bypass its bank chain.

No owner decision is needed to execute the four already-canonical persona tests, protected-integration
verification, integrated DB migration/drift checks, responsive/accessibility checks, outbox regressions,
or federated read-only qualification harnesses that create no new authority.

## Security, data-integrity, and Production gates

- Idempotency keys, deep links, document grants, and search terms are never authorization.
- Every composition surface filters before returning rows, counts, or existence.
- Own-data identity is server-resolved from authentication, never trusted from request parameters.
- Consolidation and Workforce evidence are append-only/reversible until explicit owner rules exist.
- No real Customer/Employee data, provider delivery, money movement, Payroll/tax action, OAuth, or
  Production operation belongs in acceptance.
- Production remains separately gated by accepted policy values, integrated DB qualification,
  protected integration, Preview evidence, security review, and explicit Production approval.

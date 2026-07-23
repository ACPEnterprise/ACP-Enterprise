# Workforce Capability Framework Persistence

## Boundary and terminology

Workforce Capability is a first-class domain for durable operational
qualifications, eligibility, preferences, and restrictions. It deliberately
replaces the earlier technician-only draft: Employees may be technicians,
apprentices, helpers, installers, inspectors, sales consultants, project
managers, restoration personnel, or members of future crews. A capability
profile never infers a resource classification from a title, Role, Permission,
name, Job history, Scheduling history, or free text.

Employee remains authoritative for identity, employment status and type,
Company employment, home Branch, and employment dates. Workforce Capability
references an Employee without copying those fields. No capability booleans
are added to Employee.

## Relational model

- `workforce_capability_profiles` provides one active/inactive, versioned
  aggregate root per Company Employee.
- `workforce_capability_categories` and `workforce_capabilities` are
  Company-owned catalogs. Stable normalized codes are identifiers; display
  names are presentation data.
- `workforce_profile_capabilities` records an explicit proficiency:
  `awareness`, `assisted`, `qualified`, `advanced`, or `expert`. These labels
  describe increasing technical proficiency and are authoritative entered
  facts, never performance-derived scores.
- `workforce_certifications` and `workforce_profile_certifications` separate
  definitions from credentials. Associations retain issue, expiration,
  verification, and pending/active/suspended/expired/revoked state.
- `workforce_equipment_capabilities` and
  `workforce_profile_equipment_capabilities` represent qualification to operate
  equipment. They do not mean that equipment is possessed, available, or on a
  truck.
- `workforce_branch_eligibilities` explicitly records cross-Branch eligibility.
  An Employee home Branch does not imply eligibility.
- `workforce_geographic_coverages` supports constrained postal-code or named
  territory identifiers. Maps, coordinates, radius search, routing, and
  travel-time calculation remain outside this domain. A future authoritative
  service-area domain may replace or enrich territory definitions.
- `workforce_work_restrictions` and
  `workforce_profile_work_restrictions` separate controlled definitions from
  effective restrictions. Notes are bounded operational explanations and must
  not contain medical diagnoses. Applicable restrictions are hard constraints
  for future assignment, not optional recommendation factors.
- `workforce_languages` and `workforce_language_capabilities` store explicit
  language facts. Language codes follow a constrained BCP 47-compatible shape.
  Spoken proficiency is required; reading and writing proficiency are optional.
  Language proficiency uses the distinct `basic`, `conversational`,
  `professional`, `fluent`, and `native` scale.
  Customer-facing eligibility and verified-interpreter qualification are
  distinct facts.

No catalog rows or workforce associations are seeded. Catalog administration
belongs to a future reviewed service and API milestone.

## Isolation, lifecycle, and deletion

Every table is Company-scoped. Composite foreign keys enforce Employee,
profile, catalog, Branch, and association Company consistency in PostgreSQL.
Repositories repeat Company predicates in SQL and never rely on post-query
filtering.

Catalogs and associations use explicit lifecycle values rather than hard
deletion. Aggregate, catalog, Branch, Employee, and association foreign keys
use `RESTRICT`: deleting a referenced fact cannot silently erase durable
operational history. Versioned roots and primary associations support future
optimistic concurrency. Future application services own transactions, policy,
authorization, and lifecycle transitions; repositories own SQL, deterministic
ordering, immutable projections, and row locks.

Preferences and on-call state are deferred. Availability and workload are
time-dependent operational facts and do not belong in this persistence
foundation.

## Multi-resource and intelligence readiness

The schema makes no one-technician, one-resource, or one-assignment assumption.
Future assignment domains can reference profiles for lead and assistant
resources, install teams, excavation or restoration crews, specialized
equipment operators, sales-to-install handoffs, and approved cross-Branch
sharing. Crew membership and assignment tables are intentionally absent.

Future Dispatch Intelligence and ACP-EIQ may match work requirements to
technical capabilities, certification currency, equipment qualification,
Branch eligibility, geographic coverage, restrictions, and explicit language
capability. Language matching is explainable but subordinate to licensing,
safety, restrictions, Branch eligibility, availability, required technical
capability, authorization, and durable assignment validation.

AI never owns authoritative business state. AI may interpret, analyze, and
propose; enterprise services validate and execute. Recommendations remain
advisory unless a separately approved automation policy exists, must explain
their factors, and must be auditable. Natural-language or voice interactions
must first become structured command proposals that use the same authoritative
service boundaries as every other client.

## English and Spanish readiness

English and Spanish are the initial future localization targets, but Sprint 9.1
adds no translations, localized UI, notifications, speech processing, or
conversational implementation.

Durable capability codes, lifecycle values, Permission codes, event types, and
structured command types remain language-neutral. Presentation and
communication boundaries resolve translated labels, while business rules
remain identical in English and Spanish. Customer communication preference,
workforce language capability, and application display-language preference are
separate concepts: a Spanish-speaking Employee may use an English interface,
and selecting a Spanish interface does not establish professional Spanish
proficiency.

Original user-entered language should be retained where operationally or
legally significant, and machine-translated text must be distinguishable where
accuracy matters. Future requests such as “Recommend a Spanish-speaking
qualified technician” or “ACP, mueve la cita de Daniel para hoy a las dos”
must resolve to explainable recommendations or the same validated structured
Scheduling command used for equivalent English input.

Sprint 9.1 implements no recommendation, assignment, scheduling, AI,
localization UI, crew, or conversational behavior.

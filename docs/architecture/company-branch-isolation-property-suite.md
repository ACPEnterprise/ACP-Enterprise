# Company and Branch isolation property suite

`BANK.PLAT.003` consolidates ACP's accepted tenant-isolation evidence without
changing tenancy or authorization behavior. The deterministic coverage ledger
binds each accepted domain to real repository tests and records whether the
domain is Company-scoped, Branch-scoped, platform-global, not yet applicable,
or externally sourced but Company-bound.

## Isolation model

Every protected lookup, list, mutation, relationship, event, or projection must
bind its resource Company to the authenticated `AuthorizationContext`. A
cross-Company identifier is concealed using the domain's accepted not-found or
fail-closed convention. Matching human identifiers never relax that binding.

Branch scope is explicit. Branch-scoped workflows require an authorized active
Branch. Company-wide authority may span authorized Branches only where its
domain contract says so; it never implies cross-Company access.

The reusable property runner constructs two Companies, multiple Branches,
same-shaped business identifiers, and cross-scope identities with UUIDv5. The
cases are deterministic, reproducible, and do not use flaky random fuzzing.

## Coverage and layers

The fingerprinted ledger at
`backend/tests/isolation/coverage.v1.json` covers Customers, Contacts, Service
Locations, Jobs, Scheduling, Dispatch, Workforce, Inventory, Purchasing, Price
Book, Estimates, Invoices, Payments, AP, Accounting, Business Events, Beacon,
Business Economics policy, Platform authorization, and operational projections.
The ledger also includes the authoritative Workday Time foundation introduced
during BANK.PLAT.003 reconciliation.

Evidence spans the layers each accepted architecture actually exposes:
persistence/repository, service, API, authorization, relationships, lists,
identifier allocation, Business Events, and projections. Payments and AP remain
bounded by their accepted Day-1 contracts; the ledger does not claim nonexistent
layers.

## Registration

A future domain must add one ledger entry with its scope classification, tested
layers, and exact pytest evidence. The meta-suite rejects missing files, missing
test functions, an incomplete required-domain inventory, and fingerprint drift.
High-risk relationship domains must retain explicit cross-scope relationship
evidence.

## Exclusions and gates

HCP migration rehearsal/source tables remain Migration-owned. Platform-global
technical identifiers are not tenant data. This milestone adds no persistence,
role mutation, permission mutation, deployment, Preview, or Production action.
Any future material cross-tenant failure is a security stop requiring a bounded
repair decision; the suite must not weaken an invariant to obtain a pass.

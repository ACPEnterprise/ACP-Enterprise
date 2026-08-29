# Immutable Audit Completeness Verification

## Authority and boundary

`BANK.PLAT.004` verifies accepted audit contracts; it does not create another audit system or alter domain behavior. The canonical registry is [`coverage.v1.json`](../../backend/tests/audit_completeness/coverage.v1.json), and the deterministic verifier is test-owned. Migration runtime and Engineering Control/worker-factory runtime are registered exclusions because other lanes own them.

## Audit model

Consequential operations are classified as: **A**, immutable domain audit record; **B**, immutable Business Event plus attributable domain state; **C**, append-only lifecycle/history; **D**, security/authorization audit; **E**, non-mutating read with no mutation audit; or **F**, explicitly excluded/not applicable. Different accepted domain mechanisms remain valid; a Business Event alone is not promoted to a complete audit record when actor or transition evidence is required.

Required evidence is evaluated for actor kind and identity, subject/action, occurred/effective context, Company and applicable Branch scope, command/source/idempotency lineage, immutability, and required Business Event linkage. Human, sanctioned service/system, migration, and explicit automated actors retain their real identity; system work is never attributed to a fabricated person.

## Coverage

The registry covers 23 accepted areas: Customers/Contacts/Service Locations, Jobs, Scheduling, Dispatch, Workforce, Workday Time, Inventory, Purchasing, Price Book, Estimates, Invoices/AR, Payments, AP, Accounting, Business Events, Beacon, Business Economics policy, Platform authorization, Platform audit reads, Communications, Analytics read models, and the two active-lane exclusions.

Company scope is mandatory for tenant facts. Branch scope is mandatory only where the accepted domain contract makes Branch a hard boundary; Company-wide authority remains explicit. Cross-Company or cross-Branch evidence binding fails closed. Audit-read access continues to use the existing permission catalog and scoped repository, complementing rather than duplicating BANK.PLAT.002 and BANK.PLAT.003.

## Immutability and sensitive data

The common `audit_records` table is append-only through its PostgreSQL update/delete rejection trigger. Domain evidence uses its accepted mechanisms, including immutable issuance, adjustment, estimate, invoice, journal, policy, lifecycle, and time evidence. Tests use non-production databases only. Evidence should retain identities, safe transition facts, digests, references, timestamps, actor, and scope—not credentials, secrets, private keys, raw payment material, or unnecessary source payloads.

## Determinism and extension

Contracts, evidence, and findings are canonically sorted and JSON encoded before SHA-256 fingerprinting. Identical inputs therefore produce identical findings and digest. Duplicate or contradictory identities, missing required fields, mutable evidence, and incomplete event/domain pairings fail closed.

The canonical `coverage.v1.json` registry fingerprint for this implementation is `49e35f171ac657be66727fa24f5311806fb27203dff8e4709181f62e12b85b43` (SHA-256 over sorted, compact JSON).

Every future consequential domain must add one unique registry entry, choose an audit classification and scope, and bind an existing focused evidence test. Meta-tests reject missing domains, unknown classifications, duplicate registrations, stale evidence paths, or an exclusion without a reason. A material runtime audit gap requires a separate owner-approved repair milestone; it must not be hidden by weakening the registry.

## Known limitations

This verification milestone proves architecture and repository-owned synthetic/test evidence. It performs no Preview or Production observation and does not certify physical operating procedures. Formal owner acceptance and repository-backed milestone authority remain separate from implementation completion.

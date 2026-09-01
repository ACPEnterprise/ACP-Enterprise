# BANK.ASSET.001 — operational Asset identity integration packet

## Boundary

This branch introduces one provider-neutral `Asset` identity authority for customer equipment, vehicles, individually tracked tools, operational equipment, and explicitly supported other physical assets. Identity is separate from Customer ownership, Service Location, employee or vehicle custody, Inventory quantity, maintenance, inspection, warranty eligibility, and Accounting treatment. Those facts are immutable evidence or effective-dated typed relationships.

The implementation never infers identity from a display name, serial number, VIN, plate, Customer, or Employee. It does not merge Assets. Replacement creates a predecessor link and lifecycle history; it does not rewrite the predecessor.

## Authority and safety

- Company and authorized Branch scope is applied to every read and mutation.
- Polymorphic related IDs are resolved against the authoritative Customer, Service Location, Job, Employee, Branch, Inventory Location, or vehicle Asset inside the same tenant boundary.
- Asset creation, evidence, relationships, and lifecycle commands use the Platform mutation-coverage contract, durable idempotency keys, canonical request digests, and deterministic conflict behavior.
- Identifier, inspection, maintenance, warranty, document, installation, service, readiness, and custody facts are append-only evidence.
- Lifecycle changes are row-locked, optimistic-versioned, and recorded in immutable lifecycle evidence.
- Critical evidence/history tables have PostgreSQL UPDATE/DELETE denial rules.
- Business Events contain IDs, classes, actions, and evidence digests only; protected identifier values and document paths are excluded.

## Product surface

`/assets` provides a permission-scoped Asset/Fleet directory, readiness and evidence detail, relationship history, and management-only registration. Read-only operators retain useful evidence without mutation controls. Vehicle readiness fails closed as `POLICY_REQUIRED` until explicit readiness policy/evidence exists.

## Explicit non-authorities

This increment does not create Inventory movement, dispatch, maintenance vendors, Accounting fixed assets, capitalization, depreciation, expenses, payments, payroll consequences, warranty credits, refunds, or autonomous Beacon/LIA actions. Real Company maintenance, inspection, and warranty policy values remain unconfigured.

## Migration and integration

- Revision: `h6f7d04c2a8b`
- Parents at branch creation: `g5e4c93b0f6d`, `i5h3g51b8z4x`
- The revision intentionally merges the two authoritative starting heads while adding the Asset tables; authoritative history is not rewritten.
- Enterprise must verify current ancestry at protected integration time and mechanically re-parent only if a newer authoritative head requires it.

## Preview acceptance (synthetic only)

1. Grant one user Asset read and another Asset read/manage.
2. Register synthetic customer-equipment, vehicle, and tool identities.
3. Confirm the read-only user can inspect evidence but cannot see registration controls.
4. Record synthetic identifier/readiness evidence and typed relationships through the API.
5. Confirm a vehicle without readiness evidence shows `POLICY_REQUIRED`.
6. Confirm foreign-Company/Branch object IDs fail without existence disclosure.
7. Replay each command and confirm one authoritative row/event; reuse a key with changed semantics and confirm a controlled conflict.
8. Confirm no Inventory, Accounting, Payment, Payroll, external-provider, Preview data, or Production data is mutated by Asset commands.

## Deferred successors

ASSET.001 establishes identity and evidence composition. Dedicated customer-equipment service workflows, warranty adjudication, Fleet maintenance scheduling, inspection templates, tool handoff/return commands, Beacon signals, and LIA projections require their repository-defined successor authority and should not be marked complete from this foundation alone.

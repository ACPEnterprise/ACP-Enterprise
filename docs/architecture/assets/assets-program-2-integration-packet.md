# ASSETS.FLEET.EQUIPMENT.PROGRAM.2 integration packet

## Authority and boundary

- Starting authority: `dc45adc83948953d01823cd4df2a7c3cb52a83ac`
- ASSET.001 is authoritative through protected integration `902193d` and completion evidence `6bc0a3f`.
- This increment extends that identity; it does not import the superseded ASSET.001 feature history.

The program adds one immutable typed operational-action stream for Customer equipment install/removal/replacement, warranty evidence/review, explicit Job service linkage, Fleet assignment, inspection, maintenance/out-of-service, tracked-tool custody transfer/return, and protected document binding. Asset row locking and optimistic versions serialize competing commands. Company-scoped idempotency keys and request/evidence digests make exact replay converge and contradictory replay fail closed.

## Cross-domain authority

Customer/Location, Job, Employee, Branch, vehicle, and Inventory Location identities remain authoritative in their own domains and are resolved within Company/Branch scope. Actions do not mutate Jobs, Appointments, Dispatch, Inventory quantities, Purchasing, Vendor Bills, Accounting, Payments, Economics, Beacon, LIA, or document storage.

Warranty review records evidence state only. Maintenance and inspection values remain configurable/unconfigured. Document bindings contain opaque identities, never filesystem paths or broad access grants.

## Migration

- Revision: `k7l5n83d0q6r`
- Parent: `j6k4m72c9p5q`
- Adds `operational_asset_action_evidence`, bounded history/queue indexes, unique command/evidence constraints, and PostgreSQL UPDATE/DELETE denial rules.

## Preview acceptance (synthetic only)

1. Register synthetic Customer Equipment, Fleet vehicle, and tracked-tool Assets.
2. Record Customer/Location installation, explicit Job service, warranty evidence and review.
3. Record vehicle assignment, inspection, maintenance, out-of-service evidence, and an Inventory Location relationship; verify no stock moves.
4. Record tool custody transfer and return.
5. Bind an opaque synthetic protected-document identity and verify ordinary history does not reveal paths/content.
6. Replay each command and verify one evidence row/event; reuse a key with changed semantics and verify controlled conflict.
7. Attempt foreign Customer, Location, Job, Employee, Branch, and Asset identities and verify existence-hiding rejection.
8. Confirm read-only users retain history without management controls.
9. Confirm no real data, communication, Preview deployment, Production mutation, financial posting, or Inventory movement occurs.

## Deferred configuration

Real warranty rules, inspection checklists/cadence, maintenance triggers, out-of-service policy, sensitive-identifier search policy, and provider/document delivery remain unconfigured. Their absence is policy readiness, not fabricated operational authority.

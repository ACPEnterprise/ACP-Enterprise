# ECO Payroll Migration Identity Reconciliation 1

> Superseded during integration watch: protected authority subsequently assigned
> `f6h8j0l2n4p6` to password-reset delivery. Do not integrate this packet's
> candidate. Use `eco-migration-reconciliation-integration-watch-1.md` and ECO
> successor `g7i9k1m3o5q7`.

## Result

`REAL_REVISION_ID_COLLISION`

Protected Payroll and the historical ECO persistence candidate independently
used revision `e5g7i9k1m3o5` with the same parent, but different filenames,
contents, and schema operations. Protected authority owns the Payroll revision.
This reconciliation preserves it unchanged and assigns the ECO migration the
unique successor revision `f6h8j0l2n4p6`.

The successor follows the single protected head `e5g7i9k1m3o5` at final
authority `96d67cb73dbe4838e882e1551de5906eda598f4e`. Operational measurement revision
`a1c3e5g7i9k1` is already an ancestor of that Payroll head through the accepted
Workforce/Time/Payroll chain.

## Mechanical proof

| Source | Filename | Parent | SHA-256 | Primary schema object |
|---|---|---|---|---|
| protected / Payroll PR #239 | `e5g7i9k1m3o5_create_payroll_proration_policy.py` | `d4f6h8j0l2n4` | `6f6726dfb165d7b66d2ce63084ef71c36d2bb9211927597efab40ac457859aaa` | `payroll_compensation_proration_policy_versions` |
| ECO `863cab13` | `e5g7i9k1m3o5_create_break_even_policy_events.py` | `d4f6h8j0l2n4` | `63df3edaf86d2723b701497a05067e5a935aa32801d4435c10bc7c1e6cb22f22` | `economics_break_even_policy_events` |

PR #245 is a preflight/documentation packet and contains no migration with this
revision. Its report is stale with respect to the later protected Payroll
integration; it does not provide a third migration definition.

## Enterprise integration order

1. Retain current protected authority, including the protected Payroll head
   `e5g7i9k1m3o5`.
2. Integrate this reconciliation candidate as the sole ECO wave candidate.
3. Do not integrate historical ECO candidate `863cab13` or its predecessors
   separately; their application changes are composed here.
4. Deploy only through Enterprise's normal protected process after qualification.

Expected final Alembic head: `f6h8j0l2n4p6`.

## Qualification

- Fresh PostgreSQL zero-to-head: passed.
- Alembic heads/current: one head, `f6h8j0l2n4p6`.
- Autogenerate drift: none.
- Required schema: Economics policy table and immutability trigger present;
  Payroll proration policy table present.
- Business Economics + Operational Measurement + Payroll: 462 passed.
- Changed-file Ruff, Business Economics MyPy, Python compilation, diff and
  protected-data checks: passed.

## Boundaries

This changes no owner policy value and performs no Production deployment,
Payroll execution, QBO mutation, Accounting posting, repricing, or money movement.

# ECO integration wave preflight

Date: 2026-09-12

## Authority and candidate disposition

- Current protected authority: `d4eee6f6b0bc178d58654f26f3ef2b9429332ab3`
- Composed qualification branch: `work/eco-integration-wave-preflight-1`
- Integration target: `863cab13364103b260baae7f9350b48005ac0290`

| Capability | Historical candidate | State | Enterprise action |
|---|---|---|---|
| Break-even input readiness and efficiency diagnostics | `d7ef88d1f969902d5d217fa56cb0218000c56741` | SUPERSEDED | Do not merge separately; its reconciled content is in `863cab13`. |
| Policy and scenario contracts | `fe7a9623cb3ef40fd1cd4fe0d14253b2e95c1797` | SUPERSEDED | Do not merge separately; composed by `863cab13`. |
| Calculation and explanation | `f587c271318dec93dffe458c5c3892c7e79cb511` | SUPERSEDED | Do not merge separately; composed by `863cab13`. |
| Owner policy operations and operator readiness | `37b329490a1a3a69ae59737b6a2754e6a42a9ae2` | SUPERSEDED | Do not merge separately; composed by `863cab13`. |
| SQL persistence reconciliation | `863cab13364103b260baae7f9350b48005ac0290` | READY_TO_INTEGRATE | Integrate this single composed tip after verifying protected has not moved. |
| QBO real-company evidence | `5fe1118376dbe739fcd273d3cdec03c04bf11878` | INTEGRATED | Protected successor `d4eee6f6` contains the qualified projection/readiness changes. Do not merge again. |

No candidate is currently `BLOCKED`. No separate candidate is
`RECONCILE_REQUIRED` against `d4eee6f6`; the composed merge is clean. If
protected moves, re-run this preflight before integration, especially if its
Alembic head or `break_even_readiness.py` changes.

## Exact integration order

Enterprise should integrate only `863cab13`, which already preserves this
internal dependency order:

1. measurement and input readiness;
2. operational-efficiency diagnostics;
3. typed/effective policy contract;
4. scenario model;
5. governed calculation;
6. deterministic explanation;
7. owner policy operations;
8. operator readiness and non-authoritative preview;
9. SQL policy-event persistence.

QBO accounting evidence consumption is parallel and already protected. Live
QBO OAuth is not an integration dependency. Until intended-realm production
evidence is available and reconciled, operator readiness must retain
`ACCOUNTING_NOT_RECONCILED`.

## Migration

- Current protected Alembic head: `d4f6h8j0l2n4`
- Candidate migration: `e5g7i9k1m3o5`
- Expected integrated head: `e5g7i9k1m3o5`
- Expected head count: one

The migration adds one append-only governed break-even policy-event table and
does not alter or reinterpret legacy Economics policy rows. Deployment requires
a normal database migration before application processes using the SQL adapter
are enabled. It requires no data backfill and selects no policy values.

## Qualification commands

Run from the repository root unless noted:

```bash
ENVIRONMENT=test python -m pytest -q \
  backend/tests/business_economics \
  backend/tests/operational_measurement

ruff check \
  backend/app/business_economics/break_even_*.py \
  backend/app/business_economics/operational_efficiency_diagnostics.py \
  backend/app/business_economics/owner_policy_*.py \
  backend/tests/business_economics/test_break_even_*.py \
  backend/tests/business_economics/test_operational_efficiency_diagnostics.py \
  backend/tests/business_economics/test_owner_policy_*.py \
  backend/alembic/versions/e5g7i9k1m3o5_create_break_even_policy_events.py

MYPYPATH=backend mypy \
  backend/app/business_economics/break_even_policy.py \
  backend/app/business_economics/break_even_scenario.py \
  backend/app/business_economics/break_even_calculation.py \
  backend/app/business_economics/break_even_explanation.py \
  backend/app/business_economics/owner_policy_operations.py \
  backend/app/business_economics/owner_policy_persistence.py \
  backend/app/business_economics/break_even_operator_readiness.py

python -m compileall -q backend/app/business_economics
git diff --check origin/customer-management-v1...HEAD
```

Against an empty disposable PostgreSQL database, from `backend/`:

```bash
DATABASE_URL=postgresql+asyncpg:///DISPOSABLE_DB alembic upgrade head
DATABASE_URL=postgresql+asyncpg:///DISPOSABLE_DB alembic current
DATABASE_URL=postgresql+asyncpg:///DISPOSABLE_DB alembic check
alembic heads
```

Expected: zero-to-head succeeds, `current=head=e5g7i9k1m3o5`, one head, and no
autogenerate drift.

## Post-deploy operator acceptance

Use a synthetic/non-production Company unless the owner separately authorizes
real policy entry. Prove:

1. list returns every family as unselected without supplying a default;
2. DRAFT persists and remains absent from authoritative snapshots/calculations;
3. AWAITING_APPROVAL persists and remains non-authoritative;
4. authorized approval becomes applicable only on its effective date;
5. a successor preserves the prior APPROVED event and historical replay;
6. missing policy returns grouped `POLICY_UNSELECTED` blockers;
7. draft/scenario preview is marked non-authoritative and leaves measured facts unchanged;
8. calculations retain evidence, period, Company/Branch, policy ID/version,
   scenario ID/version, and engine-version lineage;
9. identical persistence/calculation replay returns the same digests and no
   duplicate policy version;
10. accounting readiness remains `ACCOUNTING_NOT_RECONCILED` until qualified
    live QBO evidence for the intended All County realm exists.

## Hard boundaries

No protected merge, Preview deployment, Production action, policy selection,
QBO mutation, Accounting posting, repricing, Payroll execution, recommendation
automation, employment action, or money movement is authorized by this packet.

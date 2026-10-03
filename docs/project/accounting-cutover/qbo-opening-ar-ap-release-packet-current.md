# Opening-state and AR/AP control release packet

- Protected base: `e703c7b6210c62c99d2e69c44ecb0c70e09f9bc9`
- Candidate branch: `release/laptop1-qbo-banking-operator-current-1`
- Candidate: `c434aaf454c745a3d78954daf8531f5f936a1947`
- Migration head: `bw8y0a2c4e6g`
- Scope: immutable QBO opening-control evidence, balanced trial-balance
  preview, explicit opening-equity review, AR/AP control-to-subledger
  comparison, deterministic exception dispositions, replay-safe submission,
  independent approval, and governed application linkage.
- UI: protected-permission-gated QuickBooks Cutover review workspace.
- Mutations: no QBO mutation; application requires an already-posted governed
  opening journal and explicit approval authority.

## Qualification

- Focused backend and Banking regression: 61 passed.
- Frontend cutover, Banking API, and Banking workspace: 15 passed.
- Frontend TypeScript, ESLint, and production build: passed.
- Ruff, MyPy, and Python compilation: passed.
- Fresh PostgreSQL zero-to-head: passed.
- `alembic check`: passed with no drift.
- Opening migration downgrade/re-upgrade: passed.
- Exactly one Alembic head: `bw8y0a2c4e6g`.

## Physical acceptance purpose

Use a sanctioned All County QBO package to review the opening trial balance,
equity treatment, AR/AP control ties, exceptions, and approval separation.
Real balances and accountant approval remain required before GREEN.

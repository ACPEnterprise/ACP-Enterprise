# Banking closure release packet

- Protected base: `66fd912d4be1986731190b1d0603be5101d022e6`
- Candidate branch: `release/laptop1-qbo-banking-operator-current-1`
- Candidate SHA: `058a89d353798705023416c1486921af117b1f92`
- Final schema head: `bt5v7x9z1c3e`
- Scope: bank account authority, source transaction/matching adapters, operator
  import and exception workflow, reconciliation Prepare/Submit/Finance Close,
  immutable history, and protected-current migration relining.
- Real bank import, money movement, and journal mutation: NONE.
- Mobile companion: permission-gated, read-only cash/source-evidence surface;
  it does not match, post, approve, or reconcile transactions.

## Qualification

- Backend Banking tests: 36 passed.
- Frontend Banking tests: 11 passed.
- Ruff: passed.
- MyPy: passed for affected accounting modules.
- Python compilation: passed.
- ESLint: passed.
- TypeScript/Vite production build: passed.
- Fresh disposable PostgreSQL zero-to-head: passed.
- Alembic check: passed on the fresh database.
- Schema heads: exactly one, `bt5v7x9z1c3e`.
- Mobile qualification: full suite 20 suites / 159 tests passed; targeted cash
  evidence tests 2 passed; TypeScript and ESLint passed; config validation passed.
- Downgrade/re-upgrade: Banking downgrade reached the pre-Banking lineage;
  the full historical downgrade then hit the pre-existing unnamed-FK failure
  in `k3s5a7g9r123`. This is a migration-history gate for OM1E, not a Banking
  upgrade failure.

## Physical acceptance purpose

Use one sanctioned All County statement to prove import, deterministic matching,
exception review, Prepare, Submit for Review, distinct Finance Close, immutable
History, and cash-flow/report drill-down. Do not mark GREEN from this packet
alone; real evidence and accountant/operator proof remain required.

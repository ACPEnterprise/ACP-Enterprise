# Validation Standard

Validation provides evidence that a change is correct, compatible, and ready for
review. Commands are selected by affected scope; unrelated expensive checks are
not substitutes for focused coverage.

## Required selection

- **Documentation only:** inspect rendered structure, links, terminology,
  spelling, diff scope, `git diff --check`, and repository status.
- **Backend:** Ruff format check, Ruff lint, MyPy, focused tests, and the full
  backend regression suite.
- **Database:** upgrade a fresh disposable PostgreSQL database, verify current and
  head revisions, run Alembic drift checking, and remove only the disposable
  database.
- **Frontend:** strict TypeScript, ESLint, focused and full Vitest suites, and the
  production build.
- **Runtime or deployment:** build the approved artifacts and run the documented
  health, route, migration, security, and rollback checks in a disposable or
  approved non-production environment.

Use the repository's established commands and supported PostgreSQL/Redis services.
Do not claim validation that the environment could not perform. Distinguish a
product defect from contaminated test data, missing infrastructure, or a
pre-existing failure, and rerun in a clean environment when isolation matters.

## Evidence

The completion report records:

- exact checks and pass/fail totals;
- failures discovered and corrections made;
- warnings, skips, limitations, and pre-existing issues;
- migration head and drift result when applicable;
- branch, worktree, staged state, and diff integrity;
- cleanup of disposable resources.

Every failure is resolved or reported as a blocker before approval. See the
[Testing Strategy](testing-strategy.md) for test-layer expectations and the
[Definition of Done](definition-of-done.md) for the approval gate.

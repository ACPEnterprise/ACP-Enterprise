# Employee workforce source certification — Enterprise handoff

## Authority and integration order

- Starting protected authority: `bae55401586e48e4b606604c3aac1eeef4832a27`.
- Required predecessor: PR #299 at
  `57852bdf20ed9e45a5dbaaad48540358b5c9dcf1`.
- This candidate is a bounded successor to PR #299. Integrate PR #299 first, then
  this candidate. It does not replace or amend PR #299.

## Exact source certification behavior

The existing Workforce real-roster projection now includes the latest persisted
HCP Employee source-crosswalk evidence for the authorized Company. It exposes only
the source-native identifier, persisted disposition and persisted ACP Employee
target. It never links a source identity to an owner-confirmed roster person by
name, email, title or other similarity.

Each source record is classified independently as:

- `ACP_EMPLOYEE_BOUND`: its persisted ACP Employee target has an explicit audited
  real-roster binding;
- `OWNER_CERTIFICATION_REQUIRED`: it has a persisted ACP Employee target but the
  owner has not explicitly bound that Employee to the real roster;
- `SOURCE_ONLY`: the candidate source record has no persisted ACP Employee target;
- `NOT_EMPLOYEE`: the sealed migration disposition explicitly excludes it from the
  Employee population.

The owner-facing Workforce view shows exact source IDs and these states beside the
eight-person owner-confirmed roster. Source evidence remains read-only; the only
binding operation is PR #299's audited exact-Employee selection control.

## Qualification

- Focused source classification and roster contract tests: passed (5; the
  PostgreSQL binding case was separately qualified by PR #299).
- Workforce operator-route tests: passed (3).
- Ruff, MyPy, Python compilation, TypeScript, ESLint, production build and
  `git diff --check`: passed.
- Schema impact: none.

No Employee, User, Membership, credential, Branch access, role, capability,
invitation, source record, Payroll state, Customer communication, Production state
or money was mutated by this lane.

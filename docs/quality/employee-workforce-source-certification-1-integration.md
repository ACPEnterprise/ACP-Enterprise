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

For a source candidate with a persisted ACP Employee target, the source card now
lets the owner select an unbound owner-confirmed roster identity and submit that
exact target through the same audited binding command. The Employee target is
prepopulated from sealed source evidence; the owner does not retype it and ACP does
not search by name or email. Source-only candidates route to normal protected
identity onboarding after owner certification. Explicitly excluded evidence is
shown as legacy-only and cannot enter Employee onboarding from this workflow.

Source-only onboarding remains fail-closed: the current identity-onboarding model
does not persist a source-system/source-employee reference. A URL hint or random
request key is not authoritative lineage, so this candidate does not pretend to
complete that crosswalk. Enterprise must add a tenant-scoped, audited source
reference to onboarding before source-only onboarding can close automatically.

The real-roster projection also reports machine-derived aggregate totals for
login, Membership, MAIN Branch, Mobile, Dispatch-window, Timekeeping identity and
Payroll identity readiness. Payroll inputs are not evaluated or calculated.

## Qualification

- Focused source classification and roster contract tests: passed (5; the
  PostgreSQL binding case was separately qualified by PR #299).
- Workforce operator-route tests: passed (4), including exact persisted source
  target certification.
- Ruff, MyPy, Python compilation, TypeScript, ESLint, production build and
  `git diff --check`: passed.
- Schema impact: none.

No Employee, User, Membership, credential, Branch access, role, capability,
invitation, source record, Payroll state, Customer communication, Production state
or money was mutated by this lane.

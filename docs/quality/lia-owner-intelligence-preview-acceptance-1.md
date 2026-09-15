# LIA Owner Intelligence Preview Acceptance 1

## Acceptance defect

The deployed Preview release `60035693a51ec66328625dfcc78e7cd2dfead824`
predates the protected read-only owner-intelligence merge and routes the exact
question `Show me Lianne Hernandez` through the legacy unbounded fallback. The
current protected planner also had no bounded Employee-name subject resolver,
and the canonical owner role did not include the explicit Workforce read grant.
The failure therefore occurred at planner classification and subject resolution;
it was not evidence that the Employee was absent.

Repository-backed Preview acceptance evidence records Lianne Hernandez's User,
Membership, and Employee as active and canonically linked in All County / MAIN.
No credential or protected Employee value is included here.

## Bounded repair

- Recognize only the explicit `Show me <Employee name>` question form and route
  it to the Workforce source.
- Resolve an exact name inside the authenticated Company and current authorized
  Branch scope before assembling context. Zero and ambiguous matches remain
  existence-hiding, fail-closed outcomes.
- Reuse `WORKFORCE.LIA_CONTEXT.v1`; do not expose pay, tax, banking, notes, or
  unrestricted Employee history.
- Carry the server-resolved opaque Employee identity, authorization version,
  evidence digest, and source domains into follow-ups.
- Compose existing read-only Payroll operations readiness for the latest
  authoritative pay period when the principal has both Payroll reporting and
  Timekeeping administrative-read authority. Protected values remain excluded.
- Add explicit Workforce read authority to the existing owner/admin launch
  bundle and existing matching roles. The migration is additive and its
  downgrade removes only grants created by that migration.

## Expected chain

1. `Show me Lianne Hernandez` returns the minimum-necessary Workforce summary.
2. `Why is she blocked for payroll?` preserves the Employee referent and adds
   bounded Payroll readiness evidence.
3. `What do I need to provide?` preserves the same subject and evidence topics.
4. `What does the accountant need to provide?` preserves the same subject and
   states that ACP cannot assign owner/accountant responsibility without
   authoritative source evidence.

The chain is read-only. It adds no operational command, mutation tool, provider
call, transcript persistence, or Production behavior.

## Qualification

- Backend LIA, launch controls, and Workforce: 128 passed (one existing
  SQLAlchemy teardown warning).
- Frontend: 125 files / 474 tests passed.
- Ruff, MyPy, Python compilation, ESLint, TypeScript, and Vite production build:
  passed.
- Alembic: fresh zero-to-head, downgrade/re-upgrade, current=head, one head:
  passed against disposable PostgreSQL.
- `git diff --check` and credential/private-key scan: required before handoff.

Live authenticated acceptance remains deployment-gated until the protected
candidate is integrated and Preview reports that integrated release SHA.

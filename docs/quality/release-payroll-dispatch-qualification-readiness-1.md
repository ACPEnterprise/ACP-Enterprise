# Payroll and Dispatch release qualification readiness

This packet is an OM1-A release/security gate. It neither approves Payroll or
Dispatch business behavior nor authorizes Beta deployment, Payroll execution,
ACH, payment, Accounting posting, Customer communication, or Production change.

## Current authority

- Protected branch: `origin/customer-management-v1`
- Protected SHA at preparation: `5e17284374b2cb30778ee2d714a79b3d43b0b1c4`
- Canonical Alembic head: `p2r4t6v8x1z3`
- Lineage: 181 revisions, one root, one head, no structural risks
- Lineage digest: `fe185aef52cc4ff999efe871fef72454d970bbdcbb8a176278ea1a5f53200d92`

Enterprise must rerun every gate against the exact cumulative candidate. A new
protected SHA or migration head invalidates the recorded currentness evidence.

## Payroll gate

Engineering qualification is mechanically runnable, but operational release is
**NOT_READY** until OM2E supplies the cumulative first-calculation proof and
durable calculation, close, register, and paper-check evidence required by the
canonical roadmap.

The cumulative candidate must prove:

1. authentication plus Company isolation for every Payroll read and mutation;
2. Branch scope wherever the Payroll contract carries Branch authority;
3. distinct manage, calculate, review, approve, close, statement, payment-release,
   and settlement-reconciliation permissions;
4. exact mutation-registry coverage and truthful mutation classifications;
5. replay, conflicting replay, concurrency, and stale authorization/version
   rejection;
6. protected inputs are write-only, key-file backed, absent from repr/API errors,
   events, audit details, reports, logs, and artifacts;
7. closed/approved immutable results cannot be edited or silently recalculated;
8. paper-check destination and issuance evidence require explicit authority and
   remain evidence rather than money movement;
9. no real payment provider, ACH, direct-deposit, tax-payment, or bank execution
   route is enabled. The repository synthetic execution provider must remain
   test-only and reject non-test construction;
10. owner-certified real inputs and OM2E first-calculation evidence are present
    before OM1E can change this result to READY.

## Dispatch, Scheduling, and My Day gate

Engineering qualification is mechanically runnable, but operational release is
**NOT_READY** while the real Beta My Day chain remains unavailable under Issue
`#480`. The cumulative candidate must prove:

1. Customer → Job → Appointment → assignment graph continuity;
2. separate Scheduling read/manage, Dispatch read/manage, Job read/execute, and
   Employee own-day permissions;
3. Company and authorized-Branch predicates on reads and writes, with foreign
   identities concealed rather than disclosed;
4. Employee My Day resolves only the authenticated User → Membership → Employee
   identity and active primary/crew assignments;
5. reassigned, removed, inactive, canceled, or unauthorized work disappears or
   carries only the contractually authorized explicit state;
6. assignment, arrival, exception, cancellation, and reschedule replay is
   idempotent and audited without duplicate Business Events;
7. office Dispatch authority does not grant technician execution, and Mobile
   own-day authority does not grant office scheduling/dispatch administration;
8. errors remain safe and contain no foreign Customer, Job, Appointment,
   Employee, credential, or protected payload;
9. OM2E provides a qualified cumulative successor and real/sanctioned acceptance
   resolves Issue `#480` before operational release becomes READY.

## Deterministic commands

List the exact checks:

```bash
scripts/qualify-payroll-dispatch-release --plan
```

Run static security gates with repository-supported Python 3.12:

```bash
PYTHON_BIN=/path/to/python3.12 scripts/qualify-payroll-dispatch-release --static
```

Run the backend gate only against a disposable, fully migrated PostgreSQL
database—never live Preview:

```bash
ENVIRONMENT=test \
DATABASE_URL=postgresql+asyncpg://USER@127.0.0.1:5432/DISPOSABLE_DB \
ACCESS_TOKEN_KEYS='{"test":"REDACTED_TEST_KEY_AT_LEAST_32_CHARACTERS"}' \
ACCESS_TOKEN_ACTIVE_KID=test \
SECURITY_TOKEN_HMAC_KEY='REDACTED_TEST_HMAC_AT_LEAST_32_CHARACTERS' \
PYTHON_BIN=/path/to/python3.12 \
scripts/qualify-payroll-dispatch-release --backend
```

Frontend and Mobile gates are independently runnable with `--frontend` and
`--mobile`. `--all` runs every group and still requires the disposable database.
Use `scripts/enterprise-release-qualify` to seal the broader cumulative release
evidence and classify unavailable deployed checks as `BLOCKED`, never passed.

The current Mobile audit reports ten moderate package occurrences from one
advisory, `GHSA-w5hq-g745-h8pq`, through
`Expo -> @expo/config-plugins -> xcode -> uuid@7.0.3`. The affected uuid v3/v5/v6
buffer-writing API is not imported by ACP Mobile and is confined to native-project
build tooling. npm currently proposes only a breaking Expo downgrade. The checked
`release-mobile-audit-check.py` disposition fails closed on any different
advisory, package chain, direct source import, HIGH, or CRITICAL finding; it does
not hide the moderate count.

## OM1E pickup rule

OM1E should run this command after composing the OM2E cumulative successor and
before protected integration. Passing tests make the security gate eligible for
review; they do not substitute for first-calculation proof, real assignment
acceptance, deployed revision evidence, backup/rollback qualification, or owner
approval.

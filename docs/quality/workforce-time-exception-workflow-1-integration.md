# Workforce Time Exception Workflow 1 — integration qualification

## Reconciled authority

- Preserved candidate: `cb0c9e662e794147d5fd63d7f0411654f8bdc38e`.
- Reconciliation base: `567556ec5978124b41f769703d0cecc41bd05141`.
- Protected dependencies already present: `WORKFORCE.JOBSITE.HOURS.1`, Employee
  Time/Payroll cross-domain acceptance, and Payroll period/withholding register.
- Additive migration: `c2e4g6i8k0m2 -> c3e5g7i9k1m3`.

The original candidate branch remains unchanged. This reconciled branch retains the
protected Jobsite/Payroll implementations instead of replacing their files with stale
candidate variants.

## Correction authority

Paid-time corrections are immutable successor revisions. Missing clock-out, missing
interval, overlap, incorrect start, and incorrect stop are explicit classifications.
Every correction requires a non-empty explanation, derives reviewer identity from the
authenticated principal, binds a request digest and idempotency key, clears prior
approval, and requires resubmission/reapproval. Exact retry returns the accepted
revision; contradictory reuse fails closed.

Incorrect Job is deliberately not stored on paid-time evidence. It uses the protected
Job-worked interval authority. That contract preserves the original interval and
creates a successor with audit lineage; overlap and unrelated interval evidence are
rejected. This preserves the rule that paid time does not infer Job attribution.

## Dependency invalidation and recalculation

The qualifying chain is:

```text
immutable paid-time predecessor
→ corrected successor
→ resubmission and independent approval
→ new Payroll Time Input snapshot/digest
→ changed Payroll admission identity
→ deterministic gross/withholding/register recalculation contracts
```

No Payroll run, payment, Accounting posting, or Production operation is executed.
Prior snapshots and calculation evidence remain historical; corrected inputs create
new deterministic evidence rather than overwriting them.

## Qualification contract

Qualification covers original-evidence preservation, reviewer/reason evidence,
idempotent replay, contradictory replay, Branch authorization, self-approval denial,
overlap rejection, Job attribution separation, direct SQL immutability attacks,
Payroll-input invalidation, gross calculation, and Payroll reporting/register
composition. It also requires a fresh PostgreSQL upgrade, one head, `current=head`,
zero drift, downgrade/re-upgrade, frontend tests/build, Ruff, MyPy, compilation, diff
checking, and protected-data scans.

Enterprise owns protected integration. Preview and Production are out of scope.

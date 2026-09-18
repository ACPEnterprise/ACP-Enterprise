# Timekeeping Payroll approved-fact resolution 1

## Boundary

OM2-C exposes a Timekeeping-owned resolver for an already-persisted
`PayrollTimeInputRecord`. It does not calculate gross pay, taxes, deductions, or
Payroll results. No schema migration is required.

## Public interface

```python
await WorkdayTimeService.resolve_payroll_time_input_facts(
    session,
    context=context,
    payroll_input=record,
)
```

The result is a deterministic `tuple[ApprovedWorkdayTimeFact, ...]`, ordered by
work date and entry identity. The service resolves every stored revision ID,
checks Company, Employee, authorized Branch, latest-revision and approved-state
authority, reconstructs facts through `WorkdayTimeService.approved_fact`, and
reseals the canonical snapshot. Identity, version, total, and digest must all
match the persisted record.

`PayrollTimeInputResolutionError.reason` is one of:

- `invalid_reference`
- `scope_mismatch`
- `branch_scope_mismatch`
- `stale_or_ineligible`
- `snapshot_mismatch`

Missing, malformed, duplicate, cross-Company, wrong-Employee, wrong-Branch,
non-approved, superseded, changed, or otherwise unverifiable evidence fails
closed. The resolver never substitutes a successor revision for the persisted
revision ID.

## Qualification

- Fresh PostgreSQL zero-to-head migration: passed.
- PostgreSQL-backed exact reconstruction and deterministic replay: passed.
- Requested fail-closed cases, including post-seal correction: passed.
- Timekeeping and Workforce regression: 83 passed, 1 unrelated known test
  deselected.
- Payroll/Timekeeping boundary regression: 33 passed.
- Ruff, MyPy, Python compilation, and diff check: passed.

The deselected phone-safe API test currently fails at its existing router
permission dependency (`403 Permission denied`) after earlier assertions pass;
the new resolver is not reached by that route and does not change authorization
dependencies.

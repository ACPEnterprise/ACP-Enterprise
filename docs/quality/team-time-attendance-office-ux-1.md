# Team / Time & Attendance office UX qualification

## Boundary

This candidate composes the authoritative Workforce, Timekeeping, Timecard,
exception-review, and Payroll-period projections into one office workflow. It
does not add Payroll calculations, timekeeping authority, Employee onboarding
authority, or schema.

The Team surface now provides explicit Employees, Time & Attendance, and
permission-gated Payroll navigation. Employee rows identify role, Branch,
active/disabled state, and readiness without displaying internal Membership or
role identifiers. Employee detail groups personal/work identity, access, Pay
navigation, and exact Employee timecard navigation.

Time & Attendance exposes selectable pay periods, accepted and supported totals,
daily Job/non-Job attribution, open-clock, missing-clock-out, overlap,
correction revision, exception/review, and immutable audit-digest indicators.
All totals derive from accepted worked-time projections; scheduled appointment
duration is not consumed. Payroll drill-through uses the authoritative
Payroll-period readiness projection and preserves unavailable values as reasons,
not zero.

## Qualification

- Focused Workforce/Payroll navigation and API contracts: 4 files, 14 tests passed.
- Full frontend: 110 files, 391 tests passed.
- ESLint: passed.
- TypeScript and Vite production build: passed.
- `git diff --check`: passed.
- Fresh isolated PostgreSQL zero-to-head upgrade passed through
  `d4f6h8j0l2n4`.
- Timekeeping and Payroll backend: 120 tests passed under the repository's
  Python 3.12 container runtime.
- Schema/migrations: none.

## Protected integration

Enterprise should integrate this branch through the normal protected workflow,
then perform deployed office acceptance with admitted Employee/time evidence.
Fixture qualification does not constitute real Payroll acceptance and no
Payroll transmission or calculation is introduced.

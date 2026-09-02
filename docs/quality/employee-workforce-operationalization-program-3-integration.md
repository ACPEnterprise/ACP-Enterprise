# Employee Workforce Operationalization Program 3 — Integration Packet

- Starting authority: `66d22691d09598312ab83d9560013c64b82ec6f3`
- Branch: `work/employee-workforce-operationalization-program-3`
- Schema head: `k7l5n83d0q6r`
- Migration introduced: none
- Data: synthetic/non-Production only

## Boundary

This checkpoint consumes the protected Program-2 reconciliation and current
Communications, Mobile, Assets, Timekeeping, Payroll, Migration, and Enterprise
contracts. It adds a tenant-scoped, read-only onboarding preflight; requires visible
plan review before the existing atomic onboarding mutation; expands high-impact
permission review using actual mutation semantics; adds owner-morning Workforce
counts and bounded Branch/status/readiness filtering; and publishes acceptance,
adoption, and support contracts.

No provider adapter, Mobile implementation, training/crew policy, real Employee,
real invitation, Preview deployment, or Production operation is included.

## Qualification

- Fresh PostgreSQL zero-to-head: required.
- Alembic current/head/drift: required.
- Affected identity, authorization, Company Administration, onboarding, Workforce,
  Timekeeping, Pay Statement, Communications, persona, and idempotency suites:
  required.
- Frontend Vitest, ESLint, TypeScript, and Vite production build: required.
- Targeted Ruff, MyPy, Python compilation, diff/leakage checks: required.

Preview acceptance must use synthetic personas and recheck API authorization after
every navigation or session change. Physical-device execution remains with Laptop1
Mobile. Transactional provider admission remains with Laptop1-B/Communications.

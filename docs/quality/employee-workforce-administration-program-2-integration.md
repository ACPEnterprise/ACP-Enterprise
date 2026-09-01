# Employee Workforce Administration Program 2

## Integration boundary

- Starting authority: `dc45adc83948953d01823cd4df2a7c3cb52a83ac`
- Branch: `work/employee-workforce-administration-program-2`
- Data classification: synthetic/non-Production only
- Schema: no new revision; authoritative head `j6k4m72c9p5q`

This branch requalifies the Employee Administration and onboarding product against
the current repository structure. It composes canonical User, Membership, Employee,
Branch, role, permission, protected invitation, Communications, Workforce,
Timekeeping, Payroll-own-data, and Mobile contracts without creating parallel
identity or authorization systems.

## Product behavior

- Employee directory and detail remain Company/authorized-Branch scoped and include
  incomplete profiles rather than hiding them.
- Add Employee is one transactional, replay-safe identity workflow: User identity,
  Membership, Employee linkage, explicit Branch grant, canonical baseline role,
  effective-permission review, and invitation readiness.
- The actual permission catalog is grouped and described by business category,
  read/mutation/admin nature, own-data semantics, and high-impact classification.
- Canonical roles remain inspectable starting bundles. Explicit Employee variation
  uses a deterministic additive profile role in the same onboarding transaction.
  There is no invented deny ACL; a narrower baseline role is required for subtraction.
- Permission-profile creation is included in the onboarding digest, fails atomically
  for an unknown permission, converges on exact replay, and advances the new User's
  authorization version.
- Invitation authority is shown separately from Communications delivery evidence.
  Reissue and revoke retain the accepted lifecycle. Queued never means delivered;
  the current external state is truthfully `PROVIDER_NOT_CONFIGURED`.
- Workforce evidence administration is append-preserving and deterministic for
  profiles, capabilities, languages, certifications, and availability. Scheduling,
  Timekeeping, Payroll, and Dispatch retain their own authority.

## Qualification packet

Fresh PostgreSQL zero-to-head upgrade, `current == head`, and Alembic drift checks
must precede affected suites. Required coverage includes identity onboarding,
Company Administration, authorization version and Branch scope, six-persona
contracts, Workforce evidence/readiness, Timekeeping boundaries, Pay Statement
own-data, Communications delivery, and the mutation registry. Frontend acceptance
includes onboarding, Employee/Workforce Administration, full Vitest, ESLint,
TypeScript, and production build.

Preview acceptance must verify the six synthetic personas, direct API allow/deny,
permission removal/restoration, Branch revocation, Membership deactivation,
Membership-to-Employee own-data resolution, and provider-absent invitation truth.
Physical-device execution remains owned by Laptop1 Mobile; protected integration and
Preview deployment remain owned by Enterprise.

## Remaining gates

- Real proficiency, credential requirement, working-window, training, persistent
  crew, and employment lifecycle policies remain unconfigured or source-required.
- External transactional delivery requires provider configuration and separate
  authorization.
- A real Employee requires owner-supplied email, Branch, duties/role, and reviewed
  permission choices. No Lianne Hernandez record or real invitation exists here.

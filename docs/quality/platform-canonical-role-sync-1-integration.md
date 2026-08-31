# PLATFORM.CANONICAL.ROLE.SYNC.1 integration packet

## Boundary

- Starting authority: `a976fa1a18246f546140faf288e094cd10f9ddd0`
- Feature branch: `work/platform-canonical-role-sync-1`
- Intended base: `customer-management-v1`
- Schema impact: none
- Alembic head at qualification: `n2l1j60i7g3e`

This change reconciles the canonical launch-role matrix into an existing Company.
The matrix remains the single source for `SERVICE_CSR`, `OWN_DATA_ROLE`, and the
other accepted launch roles.

## Safety contract

Canonical identity is the existing immutable Company-scoped role `code` with
`is_system=true`. A non-system role with a canonical code is an unsafe identity
collision and is never converted. Reconciliation only creates missing system
roles, adds missing accepted grants, and restores system-role display metadata.
It never deletes or renames tenant roles, removes grants, changes Membership-role
assignments, or touches another Company.

The dry-run plan is deterministic and classifies every canonical role as
`ALREADY_CONFORMING`, `MISSING_CANONICAL_ROLE`,
`MISSING_CANONICAL_PERMISSION`, `CONFLICT_REQUIRES_REVIEW`, or
`UNSAFE_IDENTITY_COLLISION`. Apply locks the Company row, validates the supplied
plan digest, and commits role/grant changes, affected-user authorization-version
increments, and audit evidence in one transaction. Exact replay converges.

## Product and API

- `GET /api/v1/company-admin/canonical-roles/reconciliation` is read-only.
- `POST /api/v1/company-admin/canonical-roles/reconciliation/apply` requires role
  and permission management authority and a current plan digest.
- Administration shows readiness, conflicts, and a bounded safe-apply action;
  successful authorization changes force reauthentication.

## Qualification evidence

The isolated PostgreSQL database was freshly upgraded to the single Alembic
head. DB tests cover fresh/existing Companies, tenant-role preservation,
similarly coded custom roles, missing and partial canonical roles, stale plans,
concurrent apply, exact replay, affected-user authorization-version advancement,
cross-Company isolation, immutable audit evidence, and transactional rollback.

The canonical launch-role and physical-iPhone acceptance-contract tests cover
`TECHNICIAN`, `DISPATCHER`, `SERVICE_CSR`, `OFFICE_MANAGER`,
`COMPANY_ADMINISTRATOR`, and `OWN_DATA_ROLE`, including the existing direct API
allow/deny matrices. Preview execution and physical-device signing remain outside
this branch and owned by the centralized integration/Preview workflow.

## Integration requirements

Enterprise should run the protected checks, integrate this exact branch head,
deploy through the normal non-Production workflow, and execute the existing
synthetic Preview persona contract. No Production operation or data mutation is
part of this packet.

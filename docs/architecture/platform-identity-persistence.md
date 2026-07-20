# Platform Identity Persistence Boundaries

This document records the integrity boundary implemented by Sprint 5 Milestone 2B. It complements the Platform module definition and governs later identity services.

## Database-enforced ownership

- A membership belongs to exactly one global user and one company.
- A membership's default branch, when present, belongs to the membership company. PostgreSQL enforces this through the `company_id, default_branch_id` composite foreign key.
- An employee's home branch, when present, belongs to the employee company.
- An employee linked to a membership belongs to the same company as that membership.
- A membership can be linked to at most one employee.
- All identity and workforce foreign keys use restrictive deletion. Historical records are disabled, revoked, terminated, or archived instead of hard-deleted.

The composite foreign keys use `company_id` already required by Membership and Employee. They do not add denormalized tenant columns.

## Branch access boundary

`MembershipBranchAccess` intentionally stores only `membership_id` and `branch_id`. PostgreSQL guarantees that both records exist and that each membership/branch pair is unique. It does not guarantee that the branch belongs to the membership company.

Adding `company_id` solely to support a composite foreign key would duplicate ownership and create another value that must remain synchronized. A cross-table check constraint is not supported by PostgreSQL, and a trigger would hide policy inside procedural database code. The future membership service must therefore verify branch ownership in the same transaction before inserting or changing an assignment.

Authorization must use this rule:

1. `has_all_branch_access = true` grants access to every branch in the membership company.
2. Otherwise, only explicit `MembershipBranchAccess` rows grant branch access.
3. An empty assignment collection with `has_all_branch_access = false` grants no branch access.

The authorization evaluator must never infer unrestricted access from an empty collection.

## Role and permission boundary

Permissions are global, platform-defined capabilities with canonical uppercase codes. They do not belong to a company, user, employee, membership, or branch. Permission codes become immutable once referenced; the future permission administration service must enforce that lifecycle rule.

Roles are company-owned collections of Permissions. Memberships receive Roles through historical `MembershipRole` assignments; Users and Employees never receive Roles directly. Revoking an assignment sets `revoked_at` and retains the original record. A later reassignment creates a new row, while a partial unique index prevents more than one active Membership/Role assignment.

Authorization is additive:

- A Role with no Permission assignments grants no capabilities.
- A Membership with no active Role assignments has no role-derived Permissions.
- Missing assignments never imply access, wildcard capability, or administrator authority.
- RolePermission grants a capability but never grants Branch access.
- MembershipRole never changes or overrides `has_all_branch_access` or explicit Branch assignments.

`MembershipRole.company_id` intentionally duplicates the ownership derivable from its Membership and Role. It exists solely so PostgreSQL can enforce both composite foreign keys and reject cross-company role assignments. Services must copy the authenticated Membership company into this field; PostgreSQL verifies that it agrees with both referenced records.

The future authorization evaluator must enforce this rule:

> A request is authorized only when the Membership has the required role-derived Permission and the Membership is permitted to access the applicable Branch or resource scope.

Future services remain responsible for Permission-code immutability, Role lifecycle rules, safe handling of system Roles, transactional assignment and revocation, authorization-version invalidation, and efficient permission projection or caching.

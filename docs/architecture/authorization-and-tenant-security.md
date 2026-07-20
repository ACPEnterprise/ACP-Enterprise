# Authorization and Tenant Security

Authentication and authorization are separate Platform responsibilities. Authentication establishes a global User identity and validates its Session. Authorization resolves whether that identity may act within a specific Company and optional Branch scope.

## Central decision boundary

`AuthorizationService` is the only application service responsible for tenant authorization decisions. Business routers use reusable dependencies, and business services consume the resulting `AuthorizationContext`. Business modules must not query Membership, Role, or Permission tables to reproduce policy independently.

The request-scoped context contains:

- Authenticated User
- Active Company
- Active Membership
- Active authorized Branches
- Optional active request Branch
- Effective active Roles
- Effective active Permissions
- Current credential version
- Current authorization version

## Resolution order

Authorization resolution fails closed in this order:

1. Revalidate active, unarchived User state and credential and authorization versions.
2. Load the requested active, unarchived Company.
3. Require one active Membership for the User and Company.
4. Resolve active, unarchived Branch access.
5. Reject a requested Branch outside that set.
6. Resolve active, unrevoked company Roles.
7. Resolve active global Permissions assigned through those Roles.

Role and Permission absence grants nothing. No implicit administrator exists.

## Branch policy

When `has_all_branch_access` is true, the authorized set contains every active, unarchived Branch in the Membership Company. Otherwise, only explicit `MembershipBranchAccess` assignments grant access. An empty explicit assignment set grants no Branch access. A default Branch remains a preference and does not itself grant access.

Role-derived Permissions never expand Branch scope. A request that targets a Branch must satisfy both its required Permission and Branch authorization.

## FastAPI boundary

Requests provide `X-Company-ID` and, when applicable, `X-Branch-ID`. The authorization dependency runs only after the authenticated-identity dependency. Reusable dependency factories enforce named Permissions without embedding policy in route implementations.

An `AuthorizationContext` is request scoped. Downstream services receive it as an explicit input and use its Company, Membership, and Branch identifiers for query scoping. They must never accept an unverified tenant identifier as a substitute.

## Version invalidation

Resolution compares the access-token claims and AuthenticationSession snapshots with current `User.authorization_version` and `UserCredential.credential_version`. Any mismatch rejects the request. Role, Permission, Membership, or policy mutations that affect active access must increment the User authorization version transactionally in future administration services.

## Current boundary

This milestone establishes centralized resolution and dependency enforcement. It does not add company-administration APIs, mutation workflows, row-level security, or module-specific Permission catalogs. PostgreSQL ownership constraints remain the integrity foundation; future multi-company production hardening should add row-level security as defense in depth.

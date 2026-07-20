# Company Access-Policy Administration

## Purpose

Company access-policy administration is the controlled mutation boundary for tenant Memberships, Branch access, company Roles, Membership Role assignments, and Role Permission assignments. It builds on the authentication and authorization foundations without combining their responsibilities: authentication establishes a global User identity, authorization resolves current tenant access, and administration changes the policy used by future authorization decisions.

Business modules and routers must not write authorization tables directly. All mutations pass through `CompanyAdministrationService`, which applies tenant checks, lifecycle rules, locking, authorization-version invalidation, and operational event recording in one transaction.

## Authorization Boundary

Administration routes require an authenticated `AuthorizationContext` resolved by the centralized authorization dependency. Each route then requires one cataloged capability from `AdministrationPermission`:

| Capability | Purpose |
| --- | --- |
| `COMPANY_MEMBERSHIP_READ` | List company Memberships |
| `COMPANY_MEMBERSHIP_MANAGE` | Create Memberships and change lifecycle status |
| `COMPANY_BRANCH_ACCESS_MANAGE` | Add or remove explicit Branch access and change all-Branch access |
| `COMPANY_ROLE_READ` | List company Roles |
| `COMPANY_ROLE_MANAGE` | Create Roles, change Role status, and assign or revoke Membership Roles |
| `COMPANY_PERMISSION_MANAGE` | Assign or remove platform Permissions on company Roles |
| `COMPANY_ADMINISTER` | Identify an effective company administrator for final-administrator protection |

Permission codes are stable platform catalog values. Tenant endpoints may assign active platform Permissions to Roles, but may not create, rename, retire, or otherwise modify Permission definitions. Tenant-created Roles are never marked as system Roles through this API.

## Tenant Isolation

Every service operation scopes records to `AuthorizationContext.company.id`. A resource outside the active Company is treated as unavailable rather than exposing cross-tenant existence. The service enforces these boundaries before mutation:

- Memberships and Roles must belong to the active Company.
- Branches must belong to the active Company and be active and unarchived before assignment.
- Membership Role assignments require both records to belong to the active Company; the database also enforces their shared company ownership.
- Role Permission assignments accept only active, non-retired global Permission records.
- Users must be active and unarchived before a Membership is created or reactivated.

A default Branch is metadata only and does not grant Branch access. An empty explicit Branch assignment remains no access unless `has_all_branch_access` is explicitly true. Role assignment never changes Branch access.

## Transactions and Concurrency

Each mutation owns its transaction. The active Company row is locked first with `SELECT ... FOR UPDATE`, establishing one consistent lock order and serializing policy mutations within a Company. Target Membership, Role, User, and assignment rows are then locked where appropriate. This design favors correctness and predictable deadlock behavior for security-sensitive, relatively low-volume administrative writes.

The Company lock makes concurrent final-administrator removals coherent: after the first transaction completes, the second transaction evaluates the committed policy state and cannot remove the last remaining administrator. The same serialization prevents concurrent Branch or Role assignment changes from producing partially applied tenant policy.

## Authorization-Version Invalidation

`User.authorization_version` is the invalidation boundary for cached or token-captured authorization state. The service increments the version in the same transaction as every effective policy change:

- Membership activation, suspension, or revocation
- explicit Branch access addition or removal
- `has_all_branch_access` changes
- Membership Role assignment or revocation
- Role status changes affecting assigned Memberships
- Role Permission assignment or removal affecting assigned Memberships

Role-wide changes identify distinct affected Users and lock their User rows before incrementing every version. A transaction either commits the complete policy change and all affected versions or commits neither. Idempotent requests return the existing state without incrementing versions.

Existing access tokens and sessions capture an authorization version. After a policy mutation increments the User version, normal session and authorization-context validation rejects the stale version. A new authentication or refresh flow must obtain current authorization state before access continues.

## Lifecycle and Safety Rules

Membership creation supports invited or active status. Status mutation supports active, suspended, and revoked. Suspended and revoked Memberships resolve to no tenant access. Reactivation requires an eligible active User. The unique User/Company constraint prevents duplicate Memberships.

Roles support active, inactive, and archived states. Only active, unarchived Roles contribute Permissions. Membership Role assignments retain history by setting `revoked_at`; a revoked assignment may later be recreated as a new active assignment, while the partial unique index prevents duplicate active assignments. Role Permission assignments use the persistence model's unique assignment and are removed explicitly when the grant is withdrawn.

The final-administrator guard defines an administrator as an active Membership with an active, unrevoked Role that has the active `COMPANY_ADMINISTER` Permission. Suspending or revoking a Membership, revoking its administrative Role, deactivating that Role, or removing the defining Permission is rejected when it would leave the Company with no authorized administrator. No implicit administrator override or break-glass bypass exists in this milestone.

## Operational Security Events

Successful access-policy mutations stage controlled `BusinessEvent` records in the mutation transaction. Supported event types include Membership creation and status changes, Branch access changes, Role creation and status changes, Role assignment and revocation, and Role Permission changes. Payloads contain stable identifiers and controlled state values only; they do not contain secrets, credentials, tokens, or arbitrary exception text.

These events support operational security visibility and integration. They are not a substitute for the future Enterprise Audit platform, which will define immutable actor, before/after, retention, and compliance semantics.

## API Boundary

The `/api/v1/company-admin` router exposes narrow Membership, Branch-access, Role, Membership-Role, and Role-Permission operations. Request schemas reject unknown fields. Responses expose only policy identifiers and business state; they never expose credential hashes, token hashes, security keys, or cross-tenant details. Routers perform schema translation and dependency composition only; all policy decisions and mutations remain in the centralized service.

## Remaining Responsibilities

Future administration work must add invitation delivery, richer paginated read models, system-Role lifecycle protection beyond tenant creation, and Enterprise Audit records. Production operations also need an intentionally designed, independently controlled break-glass recovery process. None of those responsibilities should weaken the centralized authorization dependency, explicit Branch grants, final-administrator guard, or transactional version invalidation established here.

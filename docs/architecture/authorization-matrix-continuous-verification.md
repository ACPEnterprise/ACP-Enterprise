# Authorization matrix continuous verification

`BANK.PLAT.002` adds deterministic, mutation-free verification around ACP's
existing authorization system. The permission catalog, roles, memberships,
`AuthorizationContext`, backend permission dependencies, and frontend gates
remain authoritative. This checkpoint does not create another authorization
engine and never grants or revokes access.

## Verification contract

Callers project three immutable evidence sets into
`verify_authorization_matrix`:

- backend capability requirements, including the canonical permission, scope,
  branch behavior, and concrete enforcement points;
- frontend exposures for the same capability when UI actions exist; and
- role-to-permission references from an authoritative snapshot when role
  consistency is being checked.

The verifier validates these projections against `PermissionCatalog`, sorts all
identities and findings, and produces a SHA-256 fingerprint over canonical JSON.
Identical authority therefore produces identical evidence. It performs no
database, membership, role, credential, user, or permission mutation.

## Fail-closed findings

The report identifies:

- invalid or unknown permission identities;
- catalog permissions with no declared backend enforcement;
- protected capabilities without an enforcement point;
- contradictory backend declarations;
- backend/frontend permission disagreement;
- invalid role-permission references; and
- Company, platform, or branch scope disagreement.

Unknown and contradictory evidence is a failed report. Consumers may admit a
report to CI or readiness evidence, but the verifier itself does not schedule
work or alter Development Factory state.

## Ownership and integration

Domain routers and services continue to own their authorization declarations.
Frontend features continue to own their presentation gates. Platform owns only
the shared verifier and the canonical permission catalog. An adapter that
extracts declarations must preserve a stable capability identity and exact
source location; it may not infer that authentication alone is permission
authorization.

No persistence or Alembic revision is required. If durable verification history
is later required, it must receive a separately serialized schema milestone.
Preview and Production remain separately gated.

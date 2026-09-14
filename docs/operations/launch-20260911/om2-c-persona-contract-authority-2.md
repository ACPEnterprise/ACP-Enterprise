# OM2-C persona contract authority 2

Canonical authority is
`backend/operations/preview-persona-contract-authority.v1.json`. Both
`backend/scripts/acceptance_identity_provisioning_contract.py` and
`backend/scripts/authenticated_preview_acceptance.py` load that file. Neither contains
a persona permission table.

This corrected packet is pinned to protected authority
`7cdfb183c1d07e064eba88cc547df4f090708ff6`, schema head `g7i9k1m3o5q7`, and
qualified frontend SHA-256
`0fe86ebb45767edfbffeaf6c80645bf60da1860ebf141369167895da7eea97e8`.

## Blocking platform primitive

Status is `BLOCKED_MISSING_PLATFORM_SERVICE_PRINCIPAL`. Current
`AuthorizationContext` always resolves through a tenant Membership. The credential-less
Migration actor pattern also creates a tenant Membership. `AuditRecord.actor_user_id`
may be null, but null is not a deterministic durable actor identity. Therefore the
platform has no existing mechanism satisfying the required Preview-only, fixture-only,
non-authenticating, non-member audit actor.

The missing primitive is one platform service principal with identity
`preview.synthetic.fixture.orchestrator.v1`, restricted by environment and operation,
not by fabricated tenant Membership. It must be impossible in Production and against
ACP/MAIN, and every fixture create/reuse, activation, session issuance, reset, and
revocation must retain that actor identity and an audit reference. Implementing that
primitive is platform product work and is not authorized in OM2-C. Until it exists,
the provisioner and consumer fail closed and no persona can be issued.

## Interface truth

The canonical artifact labels each interface as available, partial, or missing:

- Tenant create/reuse exists, but its normal tenant `AuthorizationContext` is not
  compliant with the service-principal requirement.
- Persona provisioning and reset services exist but do not yet orchestrate all four
  deterministic personas.
- Fixture-only activation has no authoritative interface.
- Ordinary authentication exists, but a fixture-only one-hour issuance adapter without
  reusable owner credentials is missing.
- Restricted atomic token-file creation is missing.
- Attestation creation, session revocation, and OM2-C consumption exist, but attestation
  issuance is blocked until the service principal exists.

## Path decisions

| Earlier path | Decision | Current authority |
| --- | --- | --- |
| `backend/operations/preview-acceptance-identities.v1.json` | `SUPERSEDED` | `backend/operations/preview-persona-contract-authority.v1.json` |
| `backend/operations/preview-acceptance-attestation.v1.schema.json` | `RESTORE_REQUIRED` | Exact structural schema referenced by the canonical authority |
| `backend/scripts/acceptance_identity_provisioning_contract.py` | `RESTORE_REQUIRED` | Provisioning/attestation validator loading canonical authority |
| `backend/scripts/authenticated_preview_acceptance.py` | `RESTORE_REQUIRED` | Existing matrix consumer loading canonical authority |

These paths are OM2-C candidate files and are absent from current protected authority;
none is falsely described as already protected. Enterprise decides integration. The
superseded identity manifest is deleted from the candidate.

## OM1 Phone resume

Consume only the canonical artifact. Do not create personas yet. Route the missing
platform service-principal primitive, fixture activation adapter, bounded session
issuer, and restricted token writer to Enterprise/platform ownership. Resume persona
orchestration only after the canonical `audit_actor.primitive_state` becomes
`AVAILABLE`; then use the exact interfaces, fixed tenant, permission digests, mutation
maxima, schema, and filesystem contract in that artifact.

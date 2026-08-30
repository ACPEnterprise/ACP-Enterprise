# LIA foundation readiness v1

`LIA.FOUNDATION.v1` prepares ACP for a future inference provider without granting
that provider business authority. The trust order is:

authoritative domain fact → admitted measurement/finding → Beacon signal → bounded
LIA evidence → non-authoritative interpretation/recommendation → exact action
proposal → current ACP authorization → owning-domain execution.

LIA never becomes an authoritative source merely by producing text. It has no direct
database authority and no generic ACP API or mutation tool.

## Principal and retrieval authority

Every request captures the authenticated User, Membership, Company, authorized
Branches, active Branch, roles, effective permissions, credential version,
authorization version, and environment into an immutable digest. Source adapters are
selected by permission before querying. Branch-scoped adapters query only the active
Branch or the complete current authorized-Branch set. Persona labels add no privilege.

Conversation IDs are continuity hints, not authority. Every reopened conversation
must re-resolve the principal. Permission revocation, Branch removal, Membership
deactivation, or authorization-version change invalidates cached context and pending
proposals. Hidden chain-of-thought is neither requested nor persisted.

## Context and evidence

The source registry is explicit and provider-neutral. Each source declares its owner,
permission, sensitivity, Branch behavior, result limit, freshness, provenance, and
readiness. `CREDENTIAL_SECRET_NEVER_CONTEXT` is never eligible. Context budgets bound
source count, evidence count, history depth, tool attempts, and date range without
selecting a provider-specific token budget.

`EvidenceEnvelope` preserves `KNOWN`, `PARTIAL`, `STALE`, `CONFLICTING`,
`UNRESOLVED`, and `UNAVAILABLE`. Contradictions are never averaged. Material claims
bind stable evidence IDs; unsupported claims degrade to an insufficient-evidence
classification. Numerical claims require exact structured support. Temporal claims
require effective time and an accepted policy reference.

## Privacy and untrusted content

Customer notes, Job notes, imports, attachment metadata, service descriptions, email,
and provider output are untrusted data—not instructions. They cannot change principal,
scope, tools, policy, or action authority. Tool inputs forbid unknown fields and are
server-validated against Company, Branch, identity, and expected version.

Payroll context is blocked until the server can resolve Membership → Employee and
enforce own-record authority. Tax elections, bank data, deductions, credentials,
tokens, private keys, connection strings, and another Employee's protected data are
never ordinary LIA context. Customer projections must remain minimum-necessary under
the owning domain's permissions.

## Tools and actions

Every tool is versioned and declares its owning domain, permission, input schema,
scope, mutability, risk, reversibility, idempotency, approval requirement, and evidence
result. There is no generic tool. Current tools are read-only or proposal-only;
executable tool count is zero.

`LIA_PROPOSED_ACTION.v1` binds exact target, Company/Branch, principal digest,
evidence, target version, required permission, approval, risk, reversibility,
idempotency key, and expiration. It is always `PROPOSED_NOT_EXECUTED`. A future
provider candidate must pass ACP validation before proposal creation; a proposal must
then pass current authorization and owning-domain validation. Provider-to-domain
execution is prohibited.

High-risk financial, Payroll, security-administration, credential, and Production
actions remain unavailable in the initial release. Uncertain domain execution is not
blindly retried; it returns reconciliation-required/uncertain authority from the
owning domain.

## Provider boundary and initial release

The provider-neutral request contains only bounded authorized evidence, user-visible
messages, eligible tool schemas, the principal digest, context budget, and system
policy version. Candidate output is validated by evidence and tool eligibility. The
provider states are `NOT_CONFIGURED`, `AVAILABLE`, `TEMPORARILY_UNAVAILABLE`,
`RATE_LIMITED`, `TIMEOUT`, `UNCERTAIN`, and `FAILED`. Provider failure cannot mutate
or corrupt ACP authority.

`LIA.READ_ONLY.v1` allows reading, evidence-supported explanation, comparison,
summary, recommendation, navigation, and exact action preparation. It prohibits
autonomous mutation, financial execution, Payroll mutation, security administration,
and Production mutation.

Role profiles are derived from effective permissions rather than hard-coded persona
power. Mobile uses the same current Membership/Employee/Branch scope. Owner contexts
may see broader authorized sources, but never secrets or implicit Production action.

## Current source readiness

- Beacon: ready through `BEACON.INTELLIGENCE.v1`.
- Jobs, Scheduling, and Invoice status: bounded read contracts ready.
- Economics: ready through the bounded immutable `economics.owner-intelligence.v1`
  context packet; LIA does not recalculate profitability or expose Payroll detail.
- Customer operational context: partial pending a minimum-necessary domain projection.
- Payroll own statement: blocked pending server-resolved Employee identity adapter.
- System readiness: partial; only explicit bounded registries may participate.
- Provider: not configured.
- Autonomous and Production mutation: disabled.

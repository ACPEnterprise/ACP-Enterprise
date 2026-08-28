# BANK.BEA.001 — Operational exception signal catalog

## Authority and boundary

The catalog is a versioned, immutable product layer over the existing Beacon
definition, evaluation, prioritization, lifecycle, evidence, and review engine.
It does not create a second evaluator. It defines which operational exception
families ACP Enterprise recognizes and which definitions currently possess an
accepted fact adapter.

Definitions without an accepted adapter remain
`requires_authoritative_adapter`. Catalog presence is not evaluation authority.
Missing facts, inferred relationships, similarity, and unresolved source
precedence therefore cannot produce a signal.

The catalog excludes economics, profitability, Accounting policy, autonomous
remediation, notification delivery, Engineering Control, worker scheduling,
source-domain mutation, and Production behavior.

## Definition contract

Every definition contains a stable definition ID and version, operational family,
Company and optional Branch scope, subject type, named source authority,
condition, explanation-safe fields, required evidence types, deterministic base
severity and priority band, expiration policy and TTL, conflict policy, admission
state, and optional existing evaluator rule code. Canonical JSON produces the
definition digest and catalog digest.

Generated operational signal identities use UUIDv5 over the catalog and
definition digests, Company, optional Branch, subject identity, canonical evidence
digest, and sorted explicit source-evidence identities. No random identifier or
generation order participates. Company-wide scope is explicit and differs from
every Branch identity.

## Families

The catalog contains 21 definitions across:

- scheduling;
- dispatch;
- job lifecycle;
- customer and service-location operations;
- explicitly linked estimate workflow;
- invoice and payment workflow visibility; and
- workforce and technician operational eligibility.

Only overdue committed appointments and paused/intermediate jobs identify current
accepted Beacon evaluator rules. All other definitions fail closed pending an
authoritative provider-neutral adapter. Estimate workflow explicitly requires an
accepted relationship; Customer, dates, descriptions, proximity, or similarity
cannot establish identity. Invoice/payment definitions describe workflow state
only and contain no revenue-recognition, materiality, Accounting, or economic
interpretation.

## Conflict and lifecycle semantics

Ordinary definitions use `fail_closed` when accepted facts conflict. Definitions
whose condition is the existence of a conflict use
`signal_conflict_existence_only`; they may expose the conflicting evidence
identities but cannot select a winner or invent precedence.

All definitions preserve Beacon's replace-on-next-evaluation expiration policy.
Existing evaluation continues to produce deterministic evidence-bound identities,
and existing acknowledge, review, snooze, suppression, reevaluation, and cleared
condition behavior remains unchanged. The catalog API is read-only and returns
safe definition metadata in the caller's authorized Company/active-Branch context;
it returns no raw source evidence.

## Successor

`BANK.BEA.002 — Evidence-bound signal evaluation` is the next Beacon milestone.
It must admit one bounded authoritative adapter family at a time and must not
activate definitions by inference or expand into economics or autonomous actions.

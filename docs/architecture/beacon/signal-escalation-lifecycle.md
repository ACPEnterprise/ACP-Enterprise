# Beacon signal escalation lifecycle

`BANK.BEA.006` defines escalation as a deterministic Beacon attention fact,
separate from severity, priority, acknowledgement, ownership, and evaluator-
driven resolution. The bounded states are `NORMAL` and `ESCALATED`.

Every catalog definition has one version-bound eligibility registration. An
escalation-capable rule must bind the catalog definition/version, triggering
condition, required admitted evidence, any approved elapsed-time fact and
threshold, resulting state, rule version, and canonical digest. Missing policy
fails closed; freshness TTL is never treated as an escalation duration.

The current catalog contains no approved escalation rule. The two evaluable
definitions—overdue committed appointments and paused intermediate Jobs—are
`POLICY_MISSING`. The other nineteen are `NOT_EVALUABLE`. Consequently every
currently admitted operational signal projects `NORMAL`, and no escalation
transition, history row, Business Event, audit record, notification, ranking
change, or source-domain mutation is created.

An immutable transition-history contract is defined for use only after a rule
becomes authoritative. It binds previous/resulting state, signal and definition
identity, rule identity/version/digest, evidence digest, Company/Branch,
workflow version, timestamp, and explanation-safe reason. Condition clearing
will end active participation through evaluator truth while retaining history;
manual de-escalation is not supported.

The read-only readiness endpoint and operational workflow projection expose
eligibility and current state. Acknowledgement and ownership are context only:
neither suppresses escalation. BANK.BEA.004 ordering remains unchanged.

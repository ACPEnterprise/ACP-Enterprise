# ECO.MEASUREMENT.HANDOFF.1 — Calculation admission boundary

The admission contract answers only whether one verified measurement-readiness
package may be handed to a future calculation engine. It performs no economic
calculation and creates no calculation engine.

An explicit request supplies expected Company, Branch, subject, reconciliation key,
supported package and measurement versions, permitted accepted authorities, and
required policy dependency identities. Admission verifies package integrity and
replay before evaluating scope, versions, evidence acceptance/authority, policy
resolution, conflicts, and the packaged measurement gate.

Results distinguish `ADMITTED`, `REJECTED_NOT_MEASURABLE`, `REJECTED_PARTIAL`,
`REJECTED_CONFLICTING`, `REJECTED_UNRESOLVED_POLICY`, `REJECTED_INTEGRITY`,
`REJECTED_SCOPE`, and `REJECTED_AUTHORITY`. Rejection is fail-closed and deterministic.
The result retains package identity/digest, admission version, exact safe reasons,
blocking components, unresolved policies, authority limitations, explanation facts,
and a digest-derived result identity.

QBO source-reported and unaccepted public HCP evidence cannot be admitted. The
request's authority list is an explicit acceptance boundary, not source precedence:
all packaged evidence must already be accepted and permitted. Policy dependencies
must already be resolved by their owning authority; admission never resolves them.

No recognized revenue, contribution, profit, margin, leakage amount, burden, costing,
allocation, ranking, pricing, forecast, signal, recommendation, or correction is
produced.

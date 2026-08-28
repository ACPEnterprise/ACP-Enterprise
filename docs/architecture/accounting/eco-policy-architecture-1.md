# ECO.POLICY.ARCHITECTURE.1 — Generic Finance/Economics policy authority

ACP resolves Finance/Economics policy per Company and effective date. Product-level family definitions are stable identifiers; immutable Company policy versions select a strategy and parameters. No All County selection or rate is encoded here.

Company-only scope is supported in v1. The schema retains a nullable Branch identity for forward compatibility, but both database and domain contracts reject non-null Branch policy records. This avoids inventing fallback precedence. A later milestone may enable Branch overrides only with explicit, deterministic semantics.

Only explicitly approved, effective policy versions resolve. Missing, overlapping, unsupported, cross-Company, invalid-lifecycle, or scope-ambiguous policy fails closed. Drafting, reading, approval, and retirement use separate Company permissions. Approval and supersession create new durable facts; approved history is not edited or erased.

Policy references to evidence-acceptance rules are identities only. A policy does not accept or promote QBO, HCP, operational, or Accounting evidence. Those rules remain independently versioned authority contracts.

Snapshots bind Company, subject, reconciliation key, as-of date, exact policy identities/digests, and definition version. Canonical SHA-256 digests make later change detectable. Supersession affects future resolution, while a historical snapshot continues to replay its original policy context. Restatement under a new policy must create a new snapshot and future result.

The registry is extensible without conflating Job Economics labor burden with future Technician Economics. Technician attribution, compensation, worker-period costs, vehicle assignments/costs, tools/assets, multiple-worker attribution, and technician operating costs require distinct future policy families and evidence; this milestone calculates none of them.

The generic authority is sufficient to encode a future All County Finance Policy v1, but configuration remains blocked on explicit approved records and missing parameters/evidence including actual Job time, worker classes and burden rates, Job-linked inventory cost layers, accepted Job value, and attributable direct-cost linkage.

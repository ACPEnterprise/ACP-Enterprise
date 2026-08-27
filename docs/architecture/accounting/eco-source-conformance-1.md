# ECO.SOURCE.CONFORMANCE.1 — Profitability evidence conformance

This milestone adds the provider-neutral boundary between immutable public source
assertions and later Business Economics measurement. It consumes assertion metadata
and digests, not raw HCP Migration evidence, and does not adopt QBO source-reported
accounting as accepted Enterprise truth.

The assessment is deterministic across input order and classifies each required
economic component as `AVAILABLE`, `PARTIAL`, `UNKNOWN`, or `CONFLICTING`. Missing
evidence is never zero. Assertions sharing a semantic key but reporting different
value digests are retained together as a conflict; the assessment selects no winner.

The initial components are Job identity, service line, revenue, settlement, direct
labor, direct material, and overhead. A component can be `AVAILABLE` only when its
declared provenance requirements are satisfied. Finance-controlled recognition,
burden, costing, and allocation policy remain explicit missing requirements.

This enables readiness and inconsistency findings for later job, service-line, and
technician/crew profitability work. It does not calculate margin or allocate cost.
Conflicting findings may be handed to Beacon as evidence-bound signal candidates.
Beacon does not reinterpret facts; Luminary may later explain and recommend, and LIA
may guide an authorized owner. Accounting alone records corrections.

No schema, API, deployment, real source data, or Production behavior is introduced.

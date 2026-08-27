# ECO.MEASUREMENT.CONTRACT.1 — Evidence-gated contribution inputs

This contract determines whether explicitly identified Job or service-line evidence is
sufficient for a later contribution measurement. It does not perform that measurement.

Inputs cover earned-value/revenue, settlement, direct labor, labor burden, direct
material, material costing, other attributable direct costs, overhead allocation, Job
context, service-line attribution, and Accounting posting/reconciliation evidence.
Every input retains its subject and reconciliation identity, component, authority,
state, confidence, optional source value and currency/unit, effective/as-of context,
limitations, and immutable evidence/value/package digests.

The deterministic gate returns `MEASURABLE`, `PARTIALLY_MEASURABLE`,
`NOT_MEASURABLE`, or `CONFLICTING`, plus component-specific blockers. Absent values
are never zero. Different value digests remain conflicts. Source-reported QBO evidence
cannot be marked accepted for measurement. HCP-derived evidence must arrive through
the provider-neutral public handoff, and Accounting evidence must be an actually
available accepted domain/posting contract.

Revenue recognition, payment acceptance, labor burden, material costing, overhead
pools and allocation, source precedence, materiality, profitability targets, and
margin targets remain explicit versioned policy prerequisites. An unresolved policy
contains no version or evidence digest and blocks full measurement. No default policy,
profit, contribution margin, dollar leakage, forecast, price, or remediation is
created.

The gate's safe component states and immutable identities may later support Business
Economics computation and evidence-bound Beacon, Luminary, and LIA handoffs. Those
downstream behaviors remain outside this milestone.

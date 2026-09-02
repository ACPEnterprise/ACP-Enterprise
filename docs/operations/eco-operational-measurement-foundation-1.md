# ECO.OPERATIONAL.MEASUREMENT.FOUNDATION.1 integration packet

## Authority

- Protected starting authority: `origin/customer-management-v1` at `5ee0dd237ed052864c951950c1836b23f4a063b3`.
- Approved Economics policy authority `766d45416ec3705eb750d88620d30cbaaf8f93ca` is already an ancestor of protected authority.
- Successor: `work/eco-operational-measurement-foundation-1`.
- This program adds no All County policy values and creates no competing policy authority.

## Delivered boundary

`economics.operational-measurement.v1` separates measured facts and derived
measurements from policy parameters, model outputs, recommendations, and owner
decisions. It defines mechanically distinct time components, bounded ratio
input readiness, multi-Employee attribution readiness, immutable digest-bound
packets, and correction-by-successor semantics. The owner-readable endpoint is
read-only and uses the existing Economics measurement permission.

The snapshot table is append-only at the database layer. Updates and deletes
are rejected by a PostgreSQL trigger. A successor must identify its predecessor
and correction reason; a predecessor can have only one successor. Facts retain
source authority, source record identities, source version, freshness,
completeness, conflicts, sample count, limitations, and digest.

## Exact source gates

- `EXTERNAL_GATE`: travel/route duration; external market price, positioning,
  and market share.
- `SOURCE_REQUIRED`: callback/rework relationship; Fleet fuel, insurance, and
  depreciation evidence; any missing actual source record.
- `PARTIAL`: complete pause/resume interval history; Job value semantics;
  Inventory cost layers; marketing/lead identity; employer burden/benefits;
  Employee-to-Job labor attribution; native overhead classification.
- Compensation remains Payroll-owned and may appear only through authorized
  aggregate measurement. Ordinary users receive no compensation or
  cross-Employee private evidence.

## Exact policy gates

No canonical definition or threshold is selected for productive efficiency,
capacity utilization, overhead allocation, break-even, contribution/net
profit, pricing, markup, staffing, Fleet capital/depreciation, or Beacon alerts.
The Model Lab seam requires immutable historical fact digest plus a separate
approved effective-dated policy/model version and emits separately-versioned
modeled output. It is not an arbitrary-formula engine.

## Measurement composition

- Time: paid, available, scheduled, travel, arrival wait, active Job, paused
  Job, nonproductive, break, overtime, and unclassified remain distinct.
- Duration: existing Dispatch measured-duration contracts remain authoritative;
  scheduled, elapsed arrival/completion, work start/completion, pause-corrected,
  and unknown evidence cannot be substituted for one another.
- Capacity/schedule: facts may describe availability, assignments, gaps,
  overlap, timing variance, overtime, Fleet/capability constraints, and
  unclassified time. They do not attribute cause or choose a buffer.
- Conversion: lead/opportunity, presented/accepted/declined/expired Estimate,
  booked/completed Job remain separate stages and dimensions. Price correlation
  does not establish causation.
- Revenue/work: Job value, accepted Estimate, Invoice, earned work, Payment,
  settlement, and cash remain separate. Payment cannot represent performed work.
- Cost: actual labor, material movement/cost, Fleet evidence, and overhead
  evidence retain source authority. Price Book plans cannot represent actual
  duration or consumption, and incomplete contribution cannot be called net
  profit.
- Price Book/markup: configured assumptions and versions may be compared with
  actual operations later. No repricing or markup adjustment is authorized.

## Safe consumers

- Luminary receives readiness, fact lineage, and limitations only; no unsupported causality.
- Beacon receives deterministic condition names but no invented thresholds.
- LIA receives bounded read-only questions and no pricing, employment, or Accounting mutation authority.
- Scenario modeling receives provider-neutral inputs only; it cannot recommend a real staffing action in this milestone.

## Qualification evidence

The synthetic month covers three technicians, paid/available/scheduled/active/
break/unclassified time, a multi-technician Job, callback count, material
consumption, Estimate conversion stages, Invoice and Payment separation, Fleet
downtime, and partial labor attribution. Adversarial tests reject foreign
Company/Branch evidence, fabricated values behind unknown/external gates,
recommendations in fact packets, primary-technician attribution fallback, and
corrections without reasons. Packet size is capped at 10,000 facts and source
queries remain bounded; no arbitrary analytics SQL or per-record query loop is
introduced.

## Integration and environment

Enterprise should merge the isolated successor into protected authority after
review and execute migration `a1c3e5g7i9k1`. Preview and Production were not
touched. There is no Accounting posting, production deployment, policy
activation, pricing mutation, or employment action in this packet.

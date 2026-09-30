# Luminary Economic Completion Planner 4

## Boundary

This increment is a read-only projection over accepted Business Economics and
owning-domain evidence. It does not accept values, calculate missing amounts,
change Economics policy, create a Beacon recommendation, or mutate an owning
domain.

## Completion contract

`luminary.economic-completion-planner.v1` evaluates twelve explicit categories:

- field labor and Payroll burden;
- office and administrative Payroll;
- owner compensation;
- material and Job-variable cost;
- vehicles and field fixed cost;
- rent and utilities;
- insurance;
- software, professional services, and licenses;
- marketing spend;
- merchant fees;
- permits, subcontractors, disposal, and rentals; and
- other approved fixed or semi-fixed burden.

Each row retains its owning sources, responsible parties, current completeness,
missing canonical dependencies, normal product destination, blocked Economics
calculations, blocked owner decisions, and conclusions unlocked after admission.
The dependency graph is an explicit category-to-calculation-to-decision graph;
it is not inferred from labels or generated text.

## Ranking

Incomplete categories are ordered deterministically by blocked business
decisions, blocked calculations, authoritative affected Job population and
invoiced population when available, freshness, availability of a normal product
workflow, and responsible party. Missing dollar values and industry estimates
are never used.

## Owner-confirmed values

Current authority contains provisional evidence labeling and effective-dated
Economics policy, but no canonical contract for an owner-confirmed temporary
economic value. The planner therefore returns
`owner_confirmed_authority.found = false` for every category. It neither offers
an input nor treats a note as evidence. A future owning-domain decision would
need effective-dated scope, approval, provenance and value digests, retirement,
and deterministic supersession by measured evidence.

## Owner workflow

Luminary now presents a **Complete the economics model** section with the next
bounded completion item, responsible parties, authoritative source domains,
normal Twelve Hats destination, affected admitted population where available,
and the calculation or decision that becomes supportable afterward. The full
ranked matrix remains inspectable without exposing implementation terminology as
the primary experience.

## Schema and release

No schema or migration is introduced. No Production or Preview deployment is
part of this worker increment.

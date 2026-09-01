# Economics overhead and allocation evidence authority

`economics.overhead-allocation-evidence.v1` closes the engineering boundary for
`BANK.ECO.007` without selecting Company finance policy. The milestone-bank row
at the implementation base still reports `BLOCKED_DEPENDENCY` on `BANK.ECO.006`;
that row is historical scheduling evidence, not permission to infer material
utilization or overhead policy. This contract accepts only explicit authority.

## Authority boundary

An overhead-loaded result requires one approved, effective Company/Branch cost
pool; one approved, effective allocation policy; complete pool source evidence;
complete basis evidence; one currency; and exactly aligned periods. Pool and
policy identities, versions, authority digests, source digests, and the optional
predecessor allocation identity are bound into the allocation digest. Existing
immutable Economics result persistence records the allocation digest. A source
correction or policy successor therefore creates a successor result rather than
rewriting accepted history.

Supported provider-neutral basis contracts are labor hours, direct labor cost,
revenue, Job count, service-category measure, and an explicit future evidence
reference. Support is not selection. ACP provides no default basis, rate, pool,
percentage, or cost driver, and missing policy never becomes zero overhead.

Readiness is explicit: `CONFIGURED`, `UNCONFIGURED`, `INSUFFICIENT_SOURCE`,
`STALE`, `CONFLICTING`, `POLICY_REQUIRED`, or `READY`. Allocation is allowed only
at `READY`. Exact minor-unit allocation uses deterministic canonical target order
and assigns indivisible residual units in that order; the result must reconcile
exactly to the admitted pool.

## Product composition

The Business Economics workspace shows pool policy, basis policy, and source
readiness separately, lists the supported basis vocabulary, and states the owner
decision still required. Existing Luminary policy-required findings explain that
fully allocated profitability is unavailable. Existing LIA governed-assistant
classification remains `POLICY_REQUIRED` and cannot choose a policy.

Callback/warranty economics remains an external gate. Its future adapter must
provide an authoritative callback/warranty-to-Job relationship, accepted
incremental labor and material evidence, and approved overhead authority. Labels
or free text cannot establish callback identity, cost, or causality.

## Deliberate non-decisions

No All County pool, account, rate, percentage, driver, Branch treatment,
material-utilization assumption, callback policy, or Accounting mutation is
created. Existing generic Company Finance policy tables and immutable Economics
result history are reused, so this capability requires no schema migration.

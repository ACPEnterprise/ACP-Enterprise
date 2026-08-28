<!-- markdownlint-disable MD013 -->

# BANK.DF.001 — Milestone-bank ingestion contract

## Authority and boundary

This contract consumes the planning-only BANK.2 artifact introduced at
`c00aca9642874ddedafc794f8fcb4fb12fb036c6`. It is scheduler-adjacent but is not
part of scheduler execution authority. The canonical
`scheduler-manifest.v1.json` remains the sole packaged runtime manifest.

The ingestion module performs immutable file loading, fingerprint and schema
validation, provenance validation, dependency/successor reciprocity checks, cycle
rejection, gate/readiness consistency checks, and deterministic projection. It
does not repair input, persist data, create a scheduler snapshot, reconcile a
roadmap, create a command, reserve capacity, dispatch work, or approve a Start.

## Fail-closed ingestion

`load_milestone_bank()` reads only `milestone-bank.v2.json`. The SHA-256 digest is
verified against the canonical JSON payload before typed validation. Unsupported
versions, extra or missing fields, invalid identities/collision domains, duplicate
IDs or names, missing or nonreciprocal graph edges, cycles, contradictory READY or
ownership state, missing decision gates, and missing repository provenance all
raise `MilestoneBankIngestionError`. No fallback artifact or inferred correction
is permitted.

The accepted planning document is frozen into immutable Pydantic models. No model
contains a database session, runtime scheduler service, worker capacity, command,
or execution reference.

## Planning projection

`project_milestone_bank()` produces a frozen projection sorted by priority and
milestone ID. Each entry preserves:

- identity, name, and domain;
- priority and readiness classification;
- explicit blocked reasons derived from dependencies, ownership, owner/Finance
  decisions, external gates, and deferral;
- collision domain and ownership state; and
- schema-migration and Production risk.

For authoritative BANK.2 the projection contains 250 records and reports
`BANK.PUR.001` and `BANK.BEA.001` as READY. Ordering places the P0 Purchasing
candidate before the P2 Beacon candidate. Projection is visibility only; neither
candidate is dispatched or assigned.

## Scheduler and phone boundary

The live scheduler does not import this module through its manifest API, and
`scheduler/__init__.py` remains unchanged. A future approved milestone may expose
projection data to candidate selection or phone views, but it must preserve the
existing owner Start, collision, capacity, and execution gates. Displaying a
candidate can never constitute approval, assignment, dispatch, or execution.

## Successor

The recommended successor is `BANK.DF.002 — Dependency readiness evaluator`. It
may evaluate authoritative completion evidence against bank dependencies but must
remain read-only and must not dispatch work without a separately approved selection
and owner-control contract.

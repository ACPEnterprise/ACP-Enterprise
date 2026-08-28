<!-- markdownlint-disable MD013 -->

# BANK.2 — ACP Enterprise milestone bank

## Authority and purpose

This planning bank was reconciled from `origin/customer-management-v1` at
`1f012258cba67300c3481953aa18a62e12e5b634` on August 27, 2026. The machine-readable
artifact is
[`milestone-bank.v2.json`](../../backend/app/engineering_control/scheduler/milestone-bank.v2.json)
and its structural contract is
[`milestone-bank-v2.schema.json`](schemas/milestone-bank-v2.schema.json).

The bank is planning input only. It creates no Start authority, scheduler snapshot,
capacity reservation, worker enrollment, roadmap mutation, migration ownership,
Preview/Production authority, source access, or product implementation. The active
runtime manifest remains `scheduler-manifest.v1.json` and is intentionally unchanged.

## Reconciled repository state

Repository evidence supersedes older roadmap status text where they disagree.
Day-1 Accounting Core, Invoice/AR, Payments, AP, deterministic posting, and native
financial reporting are authoritative in current history. Inventory residual scope
is complete at `45fda1c`; Day-1 Field execution is complete at `4ed0780`; accepted
Economics adapters are present; and permanent worker binding is active. This does
not remove unresolved Finance activation decisions, migration source gates, or
current lane ownership.

Current ownership is recorded in the JSON artifact. Work owned by OM1, ECO,
Migration, OM2-A, Laptop1-A, or Laptop1-B is not exposed as newly executable.

## Bank shape

The bank contains 250 coherent milestones across 20 product and platform domains.
Each record has an executable boundary, hard dependency edges, collision domain,
readiness and decision gates, repository areas, validation contract, completion
evidence, and successors. Dependencies reference only IDs in this bank. Repository
commits that establish already-completed prerequisites are recorded separately as
evidence so completed historical work is not falsely reintroduced as executable.

Only `BANK.PUR.001` and `BANK.BEA.001` are `READY` at the starting authority:

- `BANK.PUR.001` is the accepted PUR.1 Vendor/PO foundation released by authoritative
  INV.2A completion. It still requires explicit owner Start and a fresh collision
  check.
- `BANK.BEA.001` is a bounded operational-signal catalog on the existing Beacon
  foundation. It excludes Economics outputs and autonomous mutation.

All other records are dependency-, owner-, Finance-, or external-gated. A `READY`
classification is never execution authority.

## Critical path

The primary P0 operational-replacement path begins with Purchasing foundation,
continues through receiving and operational Inventory/Field/Revenue workflows, and
feeds the Phase-1/Phase-2 integration, reconciliation, rehearsal, and cutover gates.
Accounting activation remains separately Finance-gated even though generic runtime
components are authoritative. Migration remains externally gated by immutable HCP/QBO
source evidence and separate rehearsal authority.

## Development Factory integration

`BANK.DF.001 — Milestone-bank ingestion contract` is the required integration
milestone. It must define reviewed mapping from BANK.2 fields into the canonical
scheduler model, dependency evaluation, collision/ownership checks, readiness
transitions, owner phone approval, and immutable execution evidence. It must not
replace the current scheduler manifest or alter active worker enrollment implicitly.

Before any bank item is dispatched, the integration must:

1. bind repository evidence to the freshly fetched authoritative SHA;
2. prove every dependency and successor edge exists and remains acyclic;
3. compare collision domains and likely paths with active worktrees;
4. preserve active ownership and require explicit owner Start;
5. serialize schema ownership from the actual single Alembic head; and
6. fail closed on owner, Finance, external, Preview, Production, or source gates.

## Validation boundary

The reproducible builder validates count, required fields, unique IDs and names,
dependency existence, reciprocal successor edges, DAG acyclicity, readiness
consistency, and duplicate executable boundaries. Schema validation, repository
reference checks, secret scanning, and Git whitespace checks are required before
publication.

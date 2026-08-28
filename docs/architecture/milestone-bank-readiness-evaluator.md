<!-- markdownlint-disable MD013 -->

# BANK.DF.002 — Dependency readiness evaluator

## Boundary

The evaluator combines the immutable, fingerprinted BANK.2 planning artifact with a separate fingerprinted authority snapshot. It emits a deterministic current-readiness projection and never changes either input. The canonical scheduler manifest remains runtime authority; this module is not imported by scheduler execution, phone Start, commands, capacity, or worker enrollment.

The authority snapshot records the repository ref and SHA reviewed, the exact BANK.2 fingerprint, an all-bank completion inventory scope, explicit BANK-to-canonical milestone identity mappings, accepted completion evidence, resolved gates, and active ownership evidence. A commit subject, branch name, filename, or documentation assertion alone is insufficient. Completion requires an explicit mapping plus an owner-accepted external-adoption record or authoritative integration acceptance with a full commit SHA and evidence reference.

Historical identities are never guessed. Duplicate mappings, completed-and-active contradictions, conflicting ownership, unknown BANK identities, bank-fingerprint mismatch, invalid collision domains, and invalid authority fingerprints fail ingestion. An absent historical identity mapping is not treated as completion.

## Evaluation

Dependencies are traversed in deterministic topological order. A predecessor satisfies a hard dependency only in `COMPLETE`; being executable or historically READY is insufficient. Completion takes precedence over historical readiness, so a completed milestone cannot be selected again. Active ownership then prevents duplication. Unresolved Finance, external, and owner gates remain fail-closed, followed by active collision domains and deferred-state checks. Only a milestone with completed predecessors, closed gates, no ownership, no collision, and consistent authority becomes `EXECUTABLE`.

The output preserves BANK priority, collision domain, gate metadata, historical readiness, explicit blocked reasons, completion identity/SHA, repository authority SHA, input fingerprints, deterministic ordering, and its own SHA-256 fingerprint. `PLANNED_READY`, `ACTIVE_OWNED`, `COMPLETE`, `EXECUTABLE`, dependency/gate/collision blocks, stale state, and invalid authority remain distinct contract terms. Invalid authority is surfaced as `ReadinessEvaluationError` before candidate projection; it never degrades into executable work.

## Current reconciliation

The packaged snapshot explicitly maps `BANK.PUR.001` to accepted `PUR.1` authority at `88285c7c0879d8df7b42659a9d25c64e5b58a27b` and `BANK.DF.001` to its accepted ingestion contract at `9940a4cfa3bdfa81ef45c1dff320dc1c4a29b8ce`. Thus the historical Purchasing READY record is now COMPLETE, not executable. Its completion releases dependency evaluation for `BANK.PLAT.001`. `BANK.BEA.001` remains independently evaluated and is not dispatched.

Accounting, Economics, Migration, operations, and other BANK records marked ACTIVE_OWNED remain unavailable until authoritative ownership release evidence exists. Their older scheduler/product identities are not silently equated with BANK identities. A later reviewed authority snapshot may add unambiguous mappings or gate releases without modifying BANK.2.

## Successor

The recommended successor is `BANK.DF.003 — Path and collision-domain evaluator`. It may deepen authoritative path-overlap and collision evidence, but selection, reservation, owner approval, dispatch, and execution remain separately authorized future work.

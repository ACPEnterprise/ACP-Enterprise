# Platform operational resilience program 1 — integration packet

- Branch: `work/platform-operational-resilience-program-1`
- Starting authority: `604bc137e512e338698a359ad577b3ada2667074`
- Reconciled authority: `8bb0d9aa010a48259f45945852583c5825e4a8c2`
- Boundary: non-Production backup/restore qualification, release consistency
  checking, bounded container logs, and operator/owner recovery contracts.
- Database migration: none.
- Production/Preview mutation: none.

## Changes

- `scripts/platform-resilience` creates restricted custom-format PostgreSQL
  backups with versioned checksum manifests, verifies them, restores only into
  distinctly named isolated databases, and detects backend/frontend/schema
  release disagreement.
- Development and Preview Compose services use bounded JSON log rotation.
- The resilience contract and runbook define state inventory, health/degraded
  semantics, continuity boundaries, owner outage guidance, restore gates,
  monitoring, RPO/RTO choices, and launch-day checks.

## Qualification evidence

- PostgreSQL 16 fresh zero-to-head: `l8m6p94e1r7s`, one head, drift clean.
- Restricted custom backup SHA-256:
  `ac70de6a1fb574e17fd7b4f275516c713f6e70bbe7d7de59c82e0e953d8b66ce`.
- Isolated restore target: `isolated-resilience-restore-20260901`.
- Restored Company/Branch/User/Membership/Employee relationship and
  authorization version validated; correlated Business Event/Audit evidence
  validated.
- Truncated backup and wrong source identity rejected.
- Matching release contract accepted; backend/frontend/schema mismatches
  rejected as `NOT_READY`.
- Redis 7 AOF restart/ping exercised; bounded PostgreSQL lock timeout exercised.
- 100 affected Platform/outbox/Communications/worker tests passed after final
  authority reconciliation; resilience tool suite contains six passing tests.
- Compose config, shell syntax, Python compilation, Ruff, and diff checks pass.

The backup and disposable database contain synthetic evidence only and live
outside Git. Enterprise owns protected integration and any Preview deployment.
Production restore remains an explicit owner/operator gate and is deliberately
refused by the tool.

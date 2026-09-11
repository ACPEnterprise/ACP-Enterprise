# OM1-ECO launch checkpoint

- Mission: `origin/work/launch-20260911-mission` at
  `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`; mission file SHA-256
  `03b74b5f065694b487268bdee531d8d50620f2816f30c91d8b665f9d5b3e9dfc`.
- Activation observed: 2026-09-10 America/New_York. Mission expiry is bounded by
  the owner instruction to 72 hours from activation; this record does not extend
  credentials or authorization.
- Lane/worktree: OM1-ECO,
  `/Users/michaelbfouse/Development/ACP-Enterprise-qbo-source-projection-1`.
- Enterprise review handoff: PR #201.
- Protected base: `42a4f68087d76247269bd4c8388f556dd62a8b5c`.
- Reconciled evidence contract: `60a1cb87` (content from qualified `ecfada39`).
- Backend implementation head: `e1b29a05a39abe2192fb4ee419ca8e1c4a868d06`.
- Task state: IMPLEMENTED and locally QUALIFIED; not protected-integrated,
  Preview-deployed, or deployed-accepted.
- Pairing dependency: OM2-B candidate `02cf4632` consumes
  `GET /api/v1/accounting/source-evidence/qbo?basis=cash|accrual`.
- Qualification: 377 combined QBO/source-projection/Economics tests and 279
  Economics/operational-measurement tests passed at the latest relevant
  checkpoints; focused Ruff, MyPy, Python compilation, and diff checks passed.
- Live source state: `LIVE_QBO_AUTHORIZATION_BLOCKED`. No production QBO runtime
  configuration, protected client/token, exact-company binding, verified realm
  marker, or production evidence root was available to this session. This does
  not prove the intended company disconnected. Historical controls remain
  historical and snapshots remain explicitly not live synchronization.
- Runtime requirement: explicit ACP Company UUID binding, protected production
  runtime/evidence roots, exact expected CompanyInfo name, production client and
  token, verified Intuit realm, and a sealed production acquisition manifest.
- Next action: Enterprise review/integration with OM2-B; when credentials become
  available, verify CompanyInfo through the production GET-only adapter,
  run bounded acquisition, publish manifest/completeness evidence, and verify the
  paired UI. Otherwise continue the approved Economics break-even input and
  productive-hour evidence readiness without policy values.
- Economics successor: capability-readiness v3 now composes the protected
  productive-hour authority instead of reporting its capacity contract absent,
  keeps workforce cost partial pending actual compensation/employer-cost evidence,
  and records the mission-authorized OM1-ECO/OM2-B QBO boundary as an external
  OAuth/realm/snapshot gate rather than the superseded Migration ownership collision.
- Evidence hardening after `e2b44319`: the projection now requires
  the protected production marker to match the snapshot realm, exact CompanyInfo
  identity/name and API minor version before describing current authorization.
  With a preserved production snapshot but no current marker it reports `stale`
  historical evidence; any contradiction fails closed.
- Break-even successor at `b930c8aa`: a deterministic Company
  input packet now composes paid, worked and productive minutes with accepted
  labor/material/direct-cost/overhead-pool/revenue-comparison evidence while
  retaining four unresolved policy gates and producing no rate, model output or
  recommendation. The underlying Company paid-time aggregation was corrected to
  use Employee paid evidence rather than Job overlap, so unassigned paid time is
  no longer silently omitted or assigned to a Job.
- OM2-B integration support after `d6b87706`: the HTTP contract now exposes
  current provider-authorization state separately from historical snapshot mode,
  plus manifest completeness, per-family entity/page counts, provider catalog
  dispositions and conflicts. OM2-B must not render its unconditional
  “Verified real-company” heading when `provider_authorization=unverified` or
  `evidence_mode=historical_snapshot`.
- OM2-B contract reconciliation after `ae2634f4`: consumer head `c1d1f7e5`
  replaced its provisional shape with `mode`, provider environment, hashed
  company identity, CompanyInfo verification time, manifest digest, bills and
  conflict packets. The backend now emits that exact required shape while
  retaining explicit authorization/completeness metadata. Only a currently
  matching protected production marker yields `mode=live`; missing authority is
  `historical` or `blocked` according to preserved evidence.
- Boundaries: no QBO writes, Accounting posting, money movement, Customer-master
  creation, HCP/QBO auto-merge, autonomous Luminary action, Preview mutation, or
  Production action.

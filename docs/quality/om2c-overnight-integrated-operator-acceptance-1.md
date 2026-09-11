# OM2-C Overnight Integrated Operator Acceptance 1

## Launch disposition

Current-authority fixture behavior is substantially qualified, but deployed
current-authority operator acceptance is **blocked**. Preview is healthy, its served
frontend index is byte-for-byte identical to the current local production build, and
protected endpoints fail unauthenticated requests with one consistent `401` body.
However, `/backend-health` reports backend version
`00e0d5f0faad31f6ff0b85cdde903857a78b70fc`, while fetched protected authority is
`36cae7427d65130cbba38b77e66b881ddc8c828f`. The reported version is 160 commits behind.
Enterprise must resolve or attest this cross-lineage release identity before a deployed
acceptance result can support launch.

No Preview or Production mutation, real Customer/Employee action, payable punch, QBO
mutation, communication, payment, Payroll execution, or Accounting posting occurred.

Machine-readable evidence is in
`docs/quality/om2c-overnight-integrated-operator-acceptance-1.json`.

## Actual source data versus fixtures

No sanctioned owner/CSR credential was available to this lane. Consequently, no
authenticated Preview response or source-data record was inspected, and no fixture
result below is represented as real-data acceptance. The public checks establish only
deployment reachability, healthy PostgreSQL/Redis dependency projection, frontend
artifact identity, authentication enforcement, and the unresolved backend release
identity.

## Current-authority fixture results

An isolated PostgreSQL database migrated from zero to the single head
`c3e5g7i9k1m3`.

- Backend intersections: 375 passed, 1 failed.
- Frontend intersections: 24 files / 98 tests passed.
- Frontend ESLint, TypeScript, and production build: passed.
- Runtime dependency audit: zero vulnerabilities.

The fixture set covers owner/CSR Customer and Location presentation, Customer → Job,
Appointment linkage, Scheduling calendar ranges, Month navigation and shared
appointment projection, authenticated Employee identity/activation contracts, own-time
and office Timecard behavior, Payroll period/register presentation, and bounded QBO
evidence that remains partial/unaccepted rather than becoming Accounting truth.

## Exact failed transitions and ownership routing

1. **Protected authority → deployed backend identity**: Preview reports `00e0d5f0…`
   instead of `36cae742…`. Route to **Enterprise deployment/release authority**. Rebuild
   or attest the backend, migrate to `c3e5g7i9k1m3`, and rerun the sanctioned Preview
   verifier before authenticated acceptance.
2. **Current Job-clock foundation → operator Job-clock API/UI**: protected authority
   contains immutable Job worked-time evidence but not the active operational API/UI
   completion. The dedicated OM2-A timekeeping worktree contains an unfinished,
   uncommitted implementation. Route to **OM2-A Job Clock/Timekeeping**; OM2-C made no
   overlapping change and performed no payable punch.
3. **Jobs schema qualification → trigger inventory assertion**:
   `test_jobs_migration_objects_and_triggers_exist` expects 6 Job-named triggers, while
   the current schema correctly contains 8 because the two append-only Job-clock tables
   add `trg_timekeeping_job_clock_events_immutable` and
   `trg_timekeeping_job_interval_revisions_immutable`. Route the stale assertion to
   **OM2-A Job Clock/Timekeeping with Jobs test ownership**. This is a test-maintenance
   failure, not a runtime product failure.
4. **Fixture acceptance → actual owner/CSR source-data acceptance**: blocked by the
   release-identity mismatch and absence of a sanctioned credential in this lane. Route
   credential/fixture admission to **Enterprise Preview operations**. QBO remains
   read-only evidence owned by **Accounting/Migration**; unavailable or unresolved
   source facts must remain partial, never zero or accepted.

## Required launch-packet continuation

After Enterprise proves the deployed backend SHA equals the approved protected SHA and
provides sanctioned synthetic owner/CSR access, reuse the existing authenticated
harness to read the deployed Customer → Location → Job → Appointment/calendar chain,
navigate previous/current/next Month boundaries, inspect Employee activation state,
inspect office Timecards, and inspect QBO evidence classification. Add Job-clock
start/stop only after its owning lane is protected and deployed, using explicitly
non-payable synthetic evidence or a read-only preexisting record. Do not manufacture a
real worked-time transition for acceptance.

No shared implementation repair belongs in this OM2-C packet.

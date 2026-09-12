# Scheduling / CSR integration wave preflight

## Authority

- Protected authority inspected: `d4eee6f6b0bc178d58654f26f3ef2b9429332ab3`.
- Protected Scheduling backend authority includes `2d8709c8`, `68cdc389`, `4514b5df`, and mutation-registry repair `9096a777`.
- Protected frontend authority includes multiview projection `8018e313`, operator calendar `857d969d`, Month/booking acceptance `f3c53990`, and reconciled CSR booking workflow `3b7b9ebe` (PR #241).

## Candidate classification

| Candidate | Classification | Integration treatment |
| --- | --- | --- |
| `e4f3a586` multiview/HCP acceptance | INTEGRATED | Patch-equivalent protected commit `8018e313`; do not reintegrate. |
| `b330da45` Scheduling/Dispatch CSR operator UX | SUPERSEDED | Product semantics are protected by `857d969d`, `f3c53990`, and `3b7b9ebe`; retain only as historical qualification. |
| `f2dbe109` CSR booking operator acceptance | SUPERSEDED | Reconciled through protected PR #241 (`3b7b9ebe`); do not merge its historical branch. |
| `27435a99` CSR operating workspace | RECONCILE_REQUIRED | Missing from protected authority; cleanly replayed as `8b515964` + `de8b6644`. |
| `7907a685` Needs Scheduling operations | RECONCILE_REQUIRED | Historical branch carries superseded ancestors; missing commits replayed as `c64064e1` + `d4f44b08`. |
| `03d9f014` recovery acceptance | RECONCILE_REQUIRED | Historical branch conflicts with PR #241 in five frontend files; only its still-relevant commits replayed as `15575bdc`, `c8859c9a`, and `44571908`. |
| This preflight branch | READY_TO_INTEGRATE | One linear, current-authority reconciliation with no unresolved conflicts. |

## Required Enterprise order

Integrate only `work/scheduling-csr-integration-wave-preflight-1`. Its linear delta from protected authority is:

1. `8b515964` — preserve CSR operating context;
2. `de8b6644` — expose location-scoped existing Jobs;
3. `c64064e1` — operational Needs Scheduling queue;
4. `d4f44b08` — queue URL restoration qualification;
5. `15575bdc` — authoritative booking/recovery behavior;
6. `c8859c9a` — Dispatch conflict refresh and stable assignment replay;
7. `44571908` — caller-owned retry identity typing;
8. this packet commit.

Do not merge the historical branches in addition to this reconciliation.

## Owner failure regression: JOB-000306

Automated contract:

1. Open the authoritative Job detail through a Scheduling return URL.
2. Enter a valid arrival-window start/end and an independent expected duration.
3. leave Technician as `Unassigned / Needs Scheduling`;
4. confirm `reserve_capacity: false`, `employee_id: null`, current `expected_job_version`, and one stable `request_id`;
5. invoke the protected `/api/v1/operations/jobs/{job_id}/schedule` authority;
6. confirm one Appointment and one Job relationship; an exact replay returns the same Appointment without duplicate evidence;
7. confirm Appointment, Job, Dispatch, technician, and queue projections refresh on both success and failure;
8. confirm stale, capacity, state, validation, authorization, timeout, service-unavailable, and uncertain outcomes retain distinct operator recovery behavior.

Deployed owner retest after Enterprise integration/deployment:

1. Open `JOB-000306`, then **Schedule Job**.
2. Set a valid local arrival window and expected duration.
3. leave Technician at **Unassigned / Needs Scheduling** and choose **Book Appointment** once.
4. wait for `SUCCEEDED`; do not infer success from navigation alone.
5. follow **Return to prior Schedule view**, refresh the browser, and reopen `JOB-000306`.
6. verify exactly one Appointment remains linked, it appears on the same local calendar day/window in Month/Day/Week/Work Week and Schedule/Dispatch, it is unassigned, and no technician capacity is reserved.
7. repeat the exact request only in a sanctioned uncertainty exercise; verify the same Appointment/result is returned and no duplicate is created.
8. in a stale/conflict exercise, change the authoritative record concurrently and verify the UI requires refresh/review rather than reporting generic success or blindly retrying.

## Qualification

- Frontend full suite: 120 files / 450 tests passed.
- Backend focused authority: 36 tests passed across Operations service, Scheduling service, and API idempotency registry.
- The initial database-independent backend invocation produced 15 passes and 21 connection-only setup errors; rerun with the isolated authenticated local PostgreSQL network passed all 36 tests.
- Required final checks: ESLint, TypeScript/Vite production build, `git diff --check`, and credential/private-key scan.

## Schema and deployment

No schema or Alembic change. No Migration admission change. No protected merge or Preview deployment was performed. Dispatch Intelligence remains review-only and non-mutating. Production, Customer communications, and autonomous Dispatch are untouched.

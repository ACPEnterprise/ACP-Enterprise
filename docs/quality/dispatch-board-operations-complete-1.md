# Dispatch board operations candidate

## Authority and boundary

- Starting protected authority: `481ada5dddc7586163bf650556abecc66269a655`
- Reconciled protected authority: `fd732c76dd6801dd4f651dc0f3f5fb8fc36a4808`
- Branch: `work/om2c-dispatch-board-operations-complete-1`
- This candidate changes the read presentation of the Dispatch board only. It does not create Employees, grant technician capability, change assignment eligibility, add lifecycle states, optimize routes, or mutate Preview or Production.
- Workforce technician authority remains owned by OM2-B. Assignment persistence remains dependent on Enterprise reconciliation/deployment of PR #299 and OM2-C candidate `69bb0193ab3486871c0c9a7ba1ce145f316477d9`.

## Product result

Dispatch now presents a deterministic operating overview from the existing authorized Dispatch and Job read models:

- bounded Customer, Job, address, technician, and state search/filtering;
- unassigned, active, exception, and completed rollups;
- Customer, Location, Job, and Appointment context in scheduled work;
- primary and additional crew visibility when authoritative assignment evidence exists;
- booked appointment counts, booked hours, and overlap visibility by technician;
- ordered next-work/location context, explicitly described as booked sequence rather than availability or autonomous routing;
- existing dispatch exception evidence with operator-facing language;
- permission separation remains intact for Dispatch read, Dispatch manage, and Job read.

Operational states are projections of the existing Appointment, Job, assignment arrival, and exception fields. This candidate does not introduce a parallel state machine. Capacity does not claim open availability where Workforce availability evidence is absent.

## Qualification

- Focused Dispatch/Scheduling frontend: 13 files / 61 tests passed.
- Candidate-specific route and utility qualification: 2 files / 12 tests passed.
- ESLint on all changed frontend files passed.
- TypeScript and production Vite build passed.
- `git diff --check` passed.
- No migration.

## Real-data acceptance gate

The public Preview health endpoints were rechecked after protected reconciliation. Preview reported backend release `fd732c76dd6801dd4f651dc0f3f5fb8fc36a4808`, database connected, and Redis connected; its public frontend artifacts were `index-BFePUMoG.js` and `index-Dq9nZZRF.css`. No sanctioned authenticated acceptance references were present. Therefore real Appointment and technician counts are `NOT_OBSERVABLE`, not zero, and no real assignment/reschedule/status mutation was attempted. Real-world closure requires deployment of this candidate and the reconciled assignment candidates, sanctioned owner/CSR and Employee authentication, and an explicitly sanctioned real record for mutation acceptance.

No synthetic acceptance records were used. Preview and Production were untouched.

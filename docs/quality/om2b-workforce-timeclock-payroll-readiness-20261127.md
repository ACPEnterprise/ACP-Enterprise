# OM2-B workforce, timeclock, and Payroll readiness evidence

Date: 2026-11-27

Implementation: `7aeaea5f84f0ae7f3eeee8a1f9db08c62e2913d8`

This packet records synthetic frontend qualification and code-path analysis. It does not claim access to, mutation of, or operational acceptance against the protected All County runtime. The reported protected empty results require Laptop Master read-only verification under its reserved `LAP-WORKFORCE-DISPATCH-READINESS-01` authority.

## Delivered correction

Supervisor time-entry correction and approval now reconcile all dependent operator views after every settled outcome, including uncertain network failures:

- supervisor timecard summary;
- detailed pay-period timecards;
- Payroll readiness and review.

No Payroll calculation, approval, close, payment, provider write, or financial transaction was executed.

## Qualification

- Focused workforce/timeclock/Payroll/technician/dispatch suite: 7 files, 46 tests passed.
- Complete frontend suite: 173 files, 802 tests passed, zero failures.
- TypeScript and production Vite build: passed.
- Focused ESLint: passed.
- Existing owner-inspection runtime at `http://127.0.0.1:18182/`: preserved and not rebuilt.

Reproduce from the exact implementation commit:

```bash
cd frontend
npm ci --cache /private/tmp/om2b-npm-cache --prefer-offline --no-audit --no-fund
npm test -- --run --maxWorkers=2
npm run build
npm exec -- eslint src/hooks/useWorkdayTime.ts src/hooks/useWorkdayTime.test.tsx
```

## Why protected results can be empty

The application contracts intentionally fail closed and do not invent workforce relationships.

| Surface | Required authoritative evidence | Empty versus configuration failure |
| --- | --- | --- |
| Dispatch | Scheduled or confirmed Appointment in the selected Branch and time window, with both arrival-window boundaries | A valid empty board means no matching admitted Appointment. Missing permissions or Branch access is an error, not an empty board. |
| Technician My Day | Active, unarchived Employee linked to the authenticated membership; active primary or crew Dispatch assignment in the service-day window; related Appointment with a complete window | Missing Employee linkage returns an explicit not-found failure. A linked Employee with no matching assignment receives an empty itinerary. |
| My time clock | Own-read permission and an Employee linked to the authenticated membership | Missing linkage or permission is rendered as onboarding/access failure. A linked Employee with no punch history is legitimately clocked out with no timecard entries. |
| Supervisor timecard | Timekeeping administration read permission, admitted Employees, and a current or selected pay period | No pay period is a configuration warning. A configured period with no recorded entries is a legitimate empty review, not Payroll evidence. |
| Payroll preparation | Payroll reporting authority, approved policy, canonical Employees, pay period, accepted time, compensation, withholding/jurisdiction, deductions, and opening/YTD evidence | Missing inputs remain explicit blockers. The UI must not infer hours, pay rates, taxes, balances, or Employees. |

## Laptop Master protected-runtime read-only checklist

Use authenticated application/API readback without database mutation:

1. Confirm the active Company, Branch scope, and permission codes for dispatcher, technician, timekeeper, and Payroll-review personas.
2. Confirm each technician account is linked to one active, unarchived Employee through the current membership.
3. Confirm the Employee has active Branch access, technician profile/capability evidence, and availability or Branch-schedule evidence.
4. Confirm the Dispatch date/window contains admitted scheduled or confirmed Appointments with complete arrival windows.
5. Confirm My Day assignments are active (`assigned`, `acknowledged`, or `reconciliation_required`) and name the linked Employee as primary technician or active crew.
6. Confirm timeclock users have own-read and own-punch authority; distinguish a clocked-out zero-history state from missing linkage.
7. Confirm a current/selected pay period exists before interpreting an empty supervisor review.
8. Confirm submitted or approved time revisions exist before expecting accepted hours or Payroll readiness.
9. Preserve source gaps as blockers; do not create Employees, assignments, punches, time revisions, or Payroll inputs solely to make protected screens non-empty.

## Browser acceptance

Use the published authenticated browser runbook and an out-of-band mode-`0600` disposable credential file. Add these operator checks to the review:

1. Dispatcher: open a synthetic scheduled Appointment, assign and reassign a synthetic eligible technician, and confirm Dispatch retains the new authority after refresh.
2. Technician: sign in as the linked synthetic technician, open My Day, and confirm only that technician's assigned visit appears.
3. Employee: clock in, start/end break, clock out, refresh, and confirm the server state and timecard revision persist.
4. Supervisor: correct a synthetic revision, submit/approve it, refresh both summary and detailed timecard, then open Payroll review and confirm readiness refreshed.
5. Verify denied personas cannot see mutation controls.
6. Record screenshot hashes and exact serving SHA. Label all records `SYNTHETIC_DISPOSABLE`; do not claim All County operational acceptance.

Owner Acceptance Finding 001 remains open.

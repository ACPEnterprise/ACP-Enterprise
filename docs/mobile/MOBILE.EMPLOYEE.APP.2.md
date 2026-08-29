# MOBILE.EMPLOYEE.APP.2 — Native Employee Timeclock

## Authority and boundaries

The ACP Employee Timeclock consumes the accepted self-service Workday endpoints: `GET /api/v1/timekeeping/me/state`, `GET /api/v1/timekeeping/me/timecard`, and `POST /api/v1/timekeeping/me/punches`. ACP Enterprise resolves User → Membership → Employee and supplies Company/Branch timezone, server UTC timestamp, transition validity, punch state, and time evidence. The client punch body contains only `action`; it never sends Employee ID or authoritative time.

No backend, schema, identity provisioning, Payroll, compensation, overtime, wage, manual-entry creation, or correction workflow is introduced.

## Client state machine

`not_clocked_in` renders Clock In. `clocked_in` renders Start Break and Clock Out. `on_break` renders End Break. The UI remains in a submitting state until an authoritative response arrives, and disables all punch actions in flight.

Each logical command receives an Expo Crypto UUID as its opaque `Idempotency-Key`. Timeout, response loss, malformed punch response, server failure, and conflict trigger authoritative state/timecard recovery. If recovery confirms a transition, server truth is displayed. If recovery confirms the previous state after an uncertain response, a user retry reuses the same key so it cannot become a second logical punch. Conflicts discard the old command after refresh.

Offline punches are prohibited and never queued. Previously confirmed display may remain visible with an explicit stale label. Connectivity restoration, app foreground, pull-to-refresh, and successful punches refresh server state. No local time database exists.

401 clears the protected session through APP.1 and routes toward sign-in. 403 shows permission denial. 422 shows identity/linkage not ready. Permission codes from `/api/v1/authorization/context` map `COMPANY_TIMEKEEPING_OWN_READ` and `COMPANY_TIMEKEEPING_OWN_PUNCH` to view/punch capabilities; hiding actions is UX only.

## My Time and accessibility

Current-period evidence displays work date, server timestamps in the entry timezone, approved duration where supplied, entry state, correction status, and distinct Employee punch versus authorized manual-entry provenance. The accepted timecard contract does not expose historical break-event rows, so the client does not invent them. Compensation and Payroll data are absent.

The surface uses safe areas, a scrollable phone-first layout, pull-to-refresh, 56-point actions, disabled-state semantics, screen-reader labels, textual state/error descriptions, and stale status that does not depend on color alone.

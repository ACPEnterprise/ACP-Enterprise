# Workforce notification targeting 1 — Enterprise handoff

## Boundary

- Protected authority: `ab5d5c5b`.
- Adds a read-only Employee notification-target resolver; no schema migration.
- Does not enqueue a notification, send email, contact APNs, or implement Mobile UI.
- Existing Dispatch assignment lifecycle and provider-neutral field notification
  seam remain unchanged.

## Contract

`GET /api/v1/workforce/employees/{employee_id}/notification-target` accepts an
exact Branch and one supported operational event:

- `NEW_ASSIGNMENT`
- `ASSIGNMENT_CHANGED`
- `JOB_CANCELED`
- `EMPLOYEE_ACTION_REQUIRED`
- `TIMEKEEPING_ISSUE`

The resolver is Company scoped and fails closed unless the exact Employee, active
Membership, active User, requested Branch authority, Employee home Branch, and
active `ACP_EMPLOYEE_MOBILE` role agree. It returns `READY` or `BLOCKED` with
transparent blockers, the current authorization version, an Employee-inbox
channel, and `PROVIDER_REQUIRED` for external push.

This is targeting authority, not delivery truth. It does not label provider
acceptance as delivery and does not include Customer contact data, Job details,
Payroll data, notification content, device tokens, credentials, or secrets.
Unknown event classes fail closed.

## Enterprise acceptance

1. Resolve each supported event for an active MAIN field Employee with Mobile
   authority; expect `READY`.
2. Independently disable the User, revoke/suspend Membership, remove Branch
   authority, remove Mobile role, and inactivate Employee; expect the matching
   blocker and never `READY`.
3. Attempt another Company's Employee ID; expect not found.
4. Attempt an unsupported financial or Payroll event; expect rejection.
5. Confirm future inbox/outbox composition re-resolves authority at delivery time
   and carries the returned authorization version as stale-authority evidence.

Qualification: Ruff, MyPy, and focused Workforce/field notification tests passed
(`9 passed`). No Preview or Production state was mutated.

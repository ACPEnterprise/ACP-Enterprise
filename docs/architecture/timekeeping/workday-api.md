# TIME.WORKDAY.API.1

## HTTP boundary

`/api/v1/timekeeping` exposes authenticated, tenant-scoped Workday Time only. The self-punch payload contains an action and optional device reference; it never accepts an Employee identity, Branch, event timestamp, elapsed duration, Job, compensation, or Payroll value. The server resolves User → Membership → Employee, derives Branch/timezone from authorization context, and records server time.

Phone clients use an opaque `Idempotency-Key` for each intended action. Retrying the same key and command returns the existing authoritative result. Reusing a key for different evidence fails closed. Impossible state transitions return conflict plus clients can query `/me/state` to recover after network uncertainty.

Manager operations use the accepted narrow permissions for manual entry, correction, approval, administrative read, and Payroll Time Input sealing. Approved history is never updated; correction creates a superseding revision that requires submission and a new managerial approval. An Employee cannot approve their own time even if a role is accidentally granted approval permission.

## Phone-first sequence

1. `GET /me/state`
2. `POST /me/punches` with `clock_in`
3. optionally `break_start` / `break_end`
4. `POST /me/punches` with `clock_out`
5. `GET /me/timecard`

Job Participation is absent from these contracts. A later phone flow may start and finish a Job while Workday Time remains clocked in.

## Intended workforce readiness

No authorized Company runtime roster or identity store was accessed in this milestone. Repository source code and synthetic tests cannot establish whether a real person has a current Employee, Membership, User, verified login, or ambiguous duplicate. Consequently each intended person is conservatively `IDENTITY_REQUIRES_OWNER_RESOLUTION` until the native Company-scoped readiness query is run against an owner-authorized environment:

- Michael Fouse
- Lianne Hernandez
- Alex Donahue
- Melvin Santiago
- Adam Mari
- Dareis Montgomery
- Dakota Wilcox
- Jason Calci

This classification does not mean the Employee is absent. It means no authorized runtime evidence was available to distinguish “linked,” “Employee only,” “requires onboarding,” or “ambiguous.” HCP identity is not inferred for any person.

## Remaining boundaries

Employee phone punching still requires a minimal authenticated mobile UI, owner-approved role assignment, and any desired device/location policy. Payroll additionally requires Payroll policy, compensation and tax authority, period admission/review, provider/filing/payment architecture, and explicit execution authorization. No compensation or economic calculation is exposed here.

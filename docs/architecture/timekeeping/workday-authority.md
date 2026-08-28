# TIME.WORKDAY.AUTHORITY.1

## Authority boundary

Workday Time is ACP's authoritative paid-time evidence and future Payroll input. Job Participation is a separate operational/economic attribution domain. Workday Time does not require a Job, and Job Participation cannot create paid time. A later reconciliation contract may associate all or part of paid time with Jobs, travel, shop/warehouse, meetings, training, breaks, PTO, or another approved activity while keeping both source assertions intact.

An Employee owns Workday Time. Employee self-service uses the existing Employee → Membership → User relationship and Enterprise authentication; no timekeeping credential system exists.

## Evidence and lifecycle

Raw `WorkdayPunchEvent` records are immutable and permanently distinguish clock-in, clock-out, break-start, and break-end. The state machine rejects a second clock-in, clock-out without an active clock-in, invalid break transitions, and non-monotonic punch timestamps.

`WorkdayTimeEntryRevision` represents a completed punched interval or authorized manual entry. Manual entries require a responsible User and reason. Every lifecycle action appends a new revision:

`RECORDED → SUBMITTED → APPROVED`

A correction appends `CORRECTED`, retains the entire prior revision lineage, clears prior approval, and must be resubmitted and reapproved. Original punch and time evidence is never overwritten. Only the latest `APPROVED` revision can enter a Payroll Time Input snapshot.

Material actions emit Company/Branch-scoped audit and Business Event evidence for punch, manual entry, submission, approval, correction, and supersession.

## Permissions

- `COMPANY_TIMEKEEPING_OWN_PUNCH`
- `COMPANY_TIMEKEEPING_OWN_READ`
- `COMPANY_TIMEKEEPING_MANUAL_ENTRY`
- `COMPANY_TIMEKEEPING_CORRECT`
- `COMPANY_TIMEKEEPING_APPROVE`
- `COMPANY_TIMEKEEPING_ADMIN_READ`

Own punch authorization additionally resolves the authenticated Membership to the target Employee. It cannot be used to punch another Employee's time. Branch access and Company foreign keys fail closed.

## Pay periods and Payroll handoff

Pay periods are explicit Company configuration with start/end, timezone, processing date, payday, schedule definition identity, and version. Overlapping periods are rejected. No product-wide weekly, held-back, or All County default exists.

Synthetic qualification uses the owner-described first target period—August 29 through September 4, 2026, processing September 10, payday September 11—only as test configuration.

`PayrollTimeInputSnapshot` deterministically seals one Employee's latest approved revisions for one pay period. It binds Company, Employee, period, entry/revision identities, correction lineage, approval evidence, total approved minutes, definition version, and digest. Replaying identical approved evidence returns the same identity. A correction/reapproval creates a different snapshot. The snapshot does not calculate wages, taxes, deductions, burden, net pay, or payment.

## Economics compatibility

The adapter emits the accepted `WorkdayTimeEvidence` shape with punch/manual provenance and approval/correction identity. It does not emit Job Participation, Job linkage, labor cost, worker burden, or an accepted Job-time assertion. Therefore it cannot close the Economics Job Participation gaps by itself.

## Next dependencies

1. `TIME.WORKDAY.API.1`: authenticated own punch/timecard and authorized manager endpoints, with rate limiting and mobile-safe responses.
2. `ECO.JOB.PARTICIPATION.AUTHORITY.1`: Job/non-Job activity attribution and reconciliation to Workday Time.
3. `PAYROLL.POLICY.AUTHORITY.1`: Company pay schedule, earning codes, overtime/leave treatment, and payroll acceptance policies.
4. `PAYROLL.TIME.ADMISSION.1`: admit sealed Payroll Time Input snapshots after period completeness and approval checks.

Employee phone punching still requires the authenticated API/UI surface, device/session controls, operating-location policy if desired, and owner-approved role assignments. September payroll additionally requires authoritative Employee payroll profiles, compensation, tax elections, earning/deduction policies, Payroll provider/filing/payment architecture, period review, and owner authorization.

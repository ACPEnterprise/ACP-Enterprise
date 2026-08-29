# All County Payroll Policy v1

Status: owner-approved activation candidate; not persisted or activated.

Configuration identity: `all-county.payroll-policy.v1`

Effective start: August 29, 2026

This Company-scoped policy records weekly Saturday-through-Friday periods in
`America/New_York`, approved Workday Time as the paid-time authority, a
40-hour weekly overtime threshold with a 1.5 multiplier, no daily overtime
Company rule, no double time, exact-minute time, no automatic break deduction,
and append-only correction treatment. Properly recorded approved unpaid breaks
are excluded. Authorized manual entries participate only with their permanent
provenance and normal approval.

PTO, vacation, sick, holiday, and other leave remain deferred pending approved
policy and entitlement evidence and do not count toward the configured overtime
threshold. Salaried timecards are attendance-only by Company default unless a
later approved policy requires them for Payroll admission. Salary is never
converted into an hourly rate by this configuration.

The first intended period is August 29–September 4, with processing targeted
for September 10 and payday September 11, 2026. These are All County schedule
facts, not ACP product defaults.

All eight intended Employee identities, pay types, effective dates, additional
earnings, worker classifications, and compensation authorities remain
unresolved. Every Employee is expected to receive phone login only after native
Employee/User/Membership resolution. No HCP identity may substitute.

Importing or building the configuration performs no persistence. Activation
later requires authoritative Company and approver identities and the existing
permission-controlled policy service. Monetary compensation must enter only
through `payroll.compensation-authority.v1`; it is absent from this document and
source code.

Admission remains `BLOCKED_IDENTITY` until native identity is resolved, then
continues to fail closed on missing compensation, policy, time, or approval.
Ready Employees may be evaluated independently, but a future final Payroll run
must disclose every blocked or excluded Employee before human approval.

This policy does not calculate, approve, pay, tax, settle, or post Payroll.

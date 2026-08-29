# All County Payroll Finance Decision Packet v1

Status: owner/Finance questionnaire; no policy selection or compensation authority
is created by this document.

Authority contracts:

- `payroll.company-policy.v1`
- `payroll.compensation-authority.v1`
- `payroll.time-input.v1`
- `payroll.calculation-admission.v1`

This packet separates non-sensitive Company policy decisions from protected
Employee compensation inputs. It is not a Payroll run, legal interpretation,
tax configuration, or authorization to pay anyone.

## Known schedule evidence, not a selected policy

Workday Time can represent the intended first period:

- work period: August 29 through September 4, 2026;
- processing target: September 10, 2026;
- payday: September 11, 2026.

These dates are evidence for the All County review only. They are not product
defaults and do not establish the workweek or overtime rule.

## Company policy decisions

### 1. Pay frequency and schedule

Question: How often is the regular All County pay period?

- `WEEKLY`: one pay period each week.
- `BIWEEKLY`: one pay period every two weeks.
- `SEMIMONTHLY`: two defined periods each month.
- `OTHER_SUPPORTED_SCHEDULE`: Finance supplies the exact repeatable calendar.

Consequence: the choice determines schedule identity, period boundaries,
processing dates, and paydays. It does not determine overtime law.

Also confirm whether the August 29–September 4 period, September 10 processing
target, and September 11 payday are correct for the first intended period.

### 2. Workweek

Question: What exact day, local time, and timezone begin All County's workweek?

Specify:

- start weekday;
- start local time;
- timezone;
- whether August 29–September 4 exactly matches that workweek.

Consequence: weekly overtime classification cannot be deterministic until this
boundary is explicit. A pay-period boundary does not silently become a legal
workweek boundary.

### 3. Regular payable time

Question: Which approved Workday Time categories qualify as regular payable
time?

- `APPROVED_WORKDAY_TIME`: only approved latest Workday revisions participate.
  Both Employee punches and authorized manual entries qualify while retaining
  distinct provenance.
- `APPROVED_WORKDAY_TIME_WITH_CATEGORY_RULES`: the same authority boundary,
  plus an explicit include/exclude list for travel, shop, meeting, training,
  other paid activity, or approved leave.

Unapproved or missing time never becomes payable zero time. Manual time cannot
masquerade as an Employee punch.

### 4. Overtime

Question: What Company-approved overtime dimensions should ACP apply, subject
to separately verified legal requirements?

Provide:

- weekly threshold, or `NOT_USED`;
- daily threshold, or `NOT_USED`;
- multiplier;
- included regular earning/time categories;
- excluded categories;
- whether approved PTO, sick, vacation, holiday, and other paid leave count
  toward an overtime threshold.

Consequence: leaving any required dimension unresolved blocks calculation; ACP
will not infer a jurisdictional rule or industry default.

### 5. Double time

Question: Does All County use a supported double-time rule?

- `NOT_USED`: explicitly no Company double-time configuration.
- `DEFERRED`: unresolved and calculation remains blocked if double time could
  apply.
- `USED`: Finance supplies threshold, multiplier, included categories,
  workweek/day context, and effective date.

### 6. Breaks

Question: How do approved breaks affect payable time?

Decide:

- unpaid break treatment;
- paid break treatment, if any;
- whether break compliance affects Payroll classification or remains a
  Timekeeping review only;
- whether automatic deduction is `PROHIBITED` or explicitly permitted under a
  separately defined rule.

No break deduction is automatic merely because a break was expected.

### 7. Rounding

Question: How is payable time measured?

- `EXACT_MINUTE`: use authoritative approved minutes without rounding.
- `APPROVED_INCREMENT`: provide increment, direction/method, application point,
  and effective date.
- `OTHER_SUPPORTED_METHOD`: provide an explicit deterministic rule.

No rounding method is inferred. Any configured method is Company-scoped and
effective-dated.

### 8. PTO, vacation, sick, holiday, and other leave

For each category that All County uses, decide:

- paid, unpaid, or not used;
- approval authority;
- evidence required for Payroll admission;
- whether an authoritative balance/accrual source exists;
- whether the category counts toward overtime thresholds;
- effective date and governing policy reference.

Missing entitlement, balance, or approval evidence cannot become paid leave.

### 9. Salaried Employees

Question: Which intended Employees, if any, use salaried compensation?

For each salaried Employee, Finance must later provide through the protected
authority path:

- approved salary amount;
- salary frequency;
- effective date;
- whether approved timecards are required for Payroll admission, attendance
  only, or not required by Company policy.

ACP will not convert salary to an hourly rate without a separately approved
calculation policy.

### 10. Payroll cutoff and blocked Employees

Question: What is the approval cutoff and who may approve time?

Decide:

- cutoff date/time relative to processing;
- authorized time-approval role(s);
- treatment of unapproved time at cutoff;
- whether one blocked Employee blocks the whole run or only that Employee;
- correction treatment before finalization.

The current architecture fails closed per Employee. It does not invent payable
time or compensation. Any broader run-level exception requires a separately
supported and approved policy.

### 11. Corrections and retroactivity

Question: Does Finance accept this append-only treatment?

- before finalization: correct, reapprove, and reseal `payroll.time-input.v1`;
- after finalization: create a new future retroactive adjustment;
- after payment: create a new future post-payment adjustment.

Answer `ACCEPT` or describe the alternative audit-preserving requirement. No
alternative may rewrite finalized or paid historical evidence.

### 12. Approval and separation of duties

Identify the intended role or named authorized operator for each function:

- time approval;
- compensation entry;
- compensation approval;
- Payroll calculation review;
- final Payroll approval;
- payment release.

State which roles must be different. The accepted authority already prevents a
policy or compensation drafter from approving the same record. Calculation,
final approval, and payment do not yet exist and remain later milestones.

## Employee identity readiness

No live identity inspection or mutation was authorized. Therefore every field
below remains unknown until the owner-authorized runtime reconciliation.

| Intended employee | ACP Employee | User | Membership | Pay type | Compensation authority | Workday self-service | Current Payroll blocker | Owner action |
|---|---|---|---|---|---|---|---|---|
| Michael Fouse | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | NOT READY | `BLOCKED_IDENTITY`, then policy/time/compensation qualification | Resolve native Employee/User/Membership; confirm pay type; enter protected compensation |
| Lianne Hernandez | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | NOT READY | `BLOCKED_IDENTITY`, then policy/time/compensation qualification | Resolve native Employee/User/Membership; confirm pay type; enter protected compensation |
| Alex Donahue | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | NOT READY | `BLOCKED_IDENTITY`, then policy/time/compensation qualification | Resolve native Employee/User/Membership; confirm pay type; enter protected compensation |
| Melvin Santiago | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | NOT READY | `BLOCKED_IDENTITY`, then policy/time/compensation qualification | Resolve native Employee/User/Membership; confirm pay type; enter protected compensation |
| Adam Mari | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | NOT READY | `BLOCKED_IDENTITY`, then policy/time/compensation qualification | Resolve native Employee/User/Membership; confirm pay type; enter protected compensation |
| Dareis Montgomery | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | NOT READY | `BLOCKED_IDENTITY`, then policy/time/compensation qualification | Resolve native Employee/User/Membership; confirm pay type; enter protected compensation |
| Dakota Wilcox | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | NOT READY | `BLOCKED_IDENTITY`, then policy/time/compensation qualification | Resolve native Employee/User/Membership; confirm pay type; enter protected compensation |
| Jason Calci | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | NOT READY | `BLOCKED_IDENTITY`, then policy/time/compensation qualification | Resolve native Employee/User/Membership; confirm pay type; enter protected compensation |

`UNKNOWN` means `OWNER_RUNTIME_RESOLUTION_REQUIRED`. HCP names or records cannot
manufacture ACP identities.

## Protected compensation input

For each resolved Employee, the protected compensation-authority workflow must
receive:

- compensation type: `HOURLY` or `SALARIED`;
- if hourly: `COMPENSATION_INPUT_REQUIRED` hourly rate and effective date;
- if salaried: `COMPENSATION_INPUT_REQUIRED` salary amount, frequency, and
  effective date;
- approved additional earning types, if applicable;
- recurring compensation components, if applicable;
- worker classification/reference, if applicable;
- approver identity and decision evidence.

Actual rates and salaries must not be written in this packet, Git, broad-access
documentation, ordinary logs, timecards, or Employee self-service responses.
They must be entered later through the permission-controlled
`payroll.compensation-authority.v1` runtime.

## Admission prerequisites

Each Employee/pay-period requires all of the following before
`READY_FOR_CALCULATION` is possible:

1. authoritative Company-scoped Employee identity;
2. correct User/Membership linkage where self-service requires it;
3. one approved, effective Company Payroll policy;
4. one approved, effective Employee compensation authority;
5. matching versioned pay-period schedule;
6. non-empty, integrity-valid, approved `payroll.time-input.v1`;
7. no scope, identity, policy, compensation, time, approval, or authority
   conflict.

Otherwise admission remains one of `BLOCKED_IDENTITY`, `BLOCKED_TIME`,
`BLOCKED_COMPENSATION`, `BLOCKED_POLICY`, `BLOCKED_APPROVAL`, or `CONFLICTING`.
Admission calculates no wages.

## Owner execution checklist after decisions

1. Approve the effective-dated All County Company Payroll policy.
2. Resolve all eight native Employee identities and required User/Membership
   links without HCP inference.
3. Enter and independently approve protected compensation authorities.
4. Configure and verify the Company pay-period schedule and first-period dates.
5. Record, submit, correct where necessary, and approve every timecard.
6. Seal one deterministic `payroll.time-input.v1` per Employee/pay period.
7. Run deterministic Payroll admission and resolve every blocker.
8. Separately authorize a future Payroll calculation milestone only after the
   intended Employees are `READY_FOR_CALCULATION`.

## Mobile Timekeeping relationship

`TIME.WORKDAY.MOBILE.1` is not required for the first Payroll when authorized
manual entries are approved and sealed. Mobile punching does require each
Employee's native Employee-to-User-to-Membership linkage, authenticated phone
session, Company scope, and deployed mobile UI. Manual and punched time may
coexist later without losing provenance.

## Later boundaries

The following are later, separately authorized milestones and are not policy
answers to fabricate here:

- wage and overtime calculation;
- Payroll taxes and filing;
- deductions and withholding;
- ACH/check generation and bank-account selection;
- Payroll approval and payment release;
- tax-agency configuration and liability settlement;
- Accounting journal generation and posting.

## Conversational owner questionnaire

Reply using the numbered structure below. Do not include wage or salary amounts
in the reply; those will use a protected entry workflow.

1. Pay frequency and first dates: `[WEEKLY / BIWEEKLY / SEMIMONTHLY / OTHER]`;
   first period dates `[CONFIRMED / corrections]`.
2. Workweek: `[weekday, local start time, timezone]`; matches first period
   `[YES / NO]`.
3. Regular payable time: `[APPROVED_WORKDAY_TIME / WITH_CATEGORY_RULES]`;
   included/excluded categories `[list]`.
4. Overtime: weekly threshold `[value / NOT_USED]`; daily threshold
   `[value / NOT_USED]`; multiplier `[value]`; included/excluded categories
   `[list]`; PTO/sick/vacation/holiday threshold treatment `[state each]`.
5. Double time: `[NOT_USED / DEFERRED / USED—with dimensions]`.
6. Breaks: unpaid treatment `[choice]`; paid treatment `[choice / NOT_USED]`;
   compliance `[PAYROLL / TIMEKEEPING_ONLY]`; auto-deduction
   `[PROHIBITED / explicit rule]`.
7. Rounding: `[EXACT_MINUTE / APPROVED_INCREMENT / OTHER]`; rule and effective
   date if applicable `[details]`.
8. Leave categories: for PTO, vacation, sick, holiday, and other, state
   `[PAID / UNPAID / NOT_USED]`, approval authority, evidence source, and
   overtime treatment.
9. Salaried Employees: identify names only `[names / NONE]`; timecard rule
   `[REQUIRED_FOR_PAYROLL / ATTENDANCE_ONLY / NOT_REQUIRED]`. Do not provide
   compensation amounts here.
10. Cutoff: `[date/time rule]`; time approver role(s) `[roles]`; unapproved-time
    treatment `[BLOCK EMPLOYEE / other supported requirement]`; one blocked
    Employee blocks `[EMPLOYEE ONLY / ENTIRE RUN]`.
11. Append-only correction model: `[ACCEPT / alternative audit-preserving
    requirement]`.
12. Separation of duties: identify roles for time approval, compensation entry,
    compensation approval, calculation review, final approval, and payment
    release; list combinations that must be prohibited.
13. Employee identity review: for each of the eight names, state
    `[NATIVE ACP EMPLOYEE KNOWN / OWNER RUNTIME RESOLUTION REQUIRED]` and whether
    phone login is intended `[YES / NO]`.
14. Compensation readiness: for each Employee, state only `[HOURLY / SALARIED /
    UNRESOLVED]`, effective-date readiness `[READY / UNRESOLVED]`, additional
    earning categories, worker classification/reference if used, and intended
    compensation approver. Enter monetary values later through the protected
    runtime, never in this response.

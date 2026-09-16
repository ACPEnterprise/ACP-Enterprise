# Real Employee cutover readiness — integration-wait packet

## Authority and limits

- Protected authority inspected: `b5c8f427d48028144d58cf7a76e6f4a33729feb5`.
- Pending order: PR #299, then PR #311.
- Owner-confirmed roster: eight people; five Field Technicians.
- The private Migration acceptance plan contains source identifiers and is not in
  Git. This packet therefore does not invent source IDs, display identities or
  Appointment rows. Exact source/current-work matrices must be generated from the
  sanctioned evidence store or deployed authenticated projections.

## Eight-person readiness baseline

| Person | Classification | Required role authority | Current status before deployment |
| --- | --- | --- | --- |
| Michael Fouse | Administrator | `COMPANY_ADMINISTRATOR` | Owner certification required |
| Lianne Hernandez | Office Manager | `OFFICE_MANAGER` | Prior login evidence exists; refresh from deployed authority required |
| Alex Donahue | Office Staff | `SERVICE_CSR` | Owner certification required |
| Melvin Santiago | Field Technician | `TECHNICIAN`, `ACP_EMPLOYEE_MOBILE` | Owner certification required |
| Adam Mari | Field Technician | `TECHNICIAN`, `ACP_EMPLOYEE_MOBILE` | Owner certification required |
| Dareis Montgomery | Field Technician | `TECHNICIAN`, `ACP_EMPLOYEE_MOBILE` | Owner certification required |
| Dakota Wilcox | Field Technician | `TECHNICIAN`, `ACP_EMPLOYEE_MOBILE` | Owner certification required |
| Jason Calci | Field Technician | `TECHNICIAN`, `ACP_EMPLOYEE_MOBILE` | Owner certification required |

Unavailable runtime evidence is not classified as false. After deployment, PR
#311 returns exact independent states for binding, User, credential, Membership,
MAIN Branch, role, Mobile, capability, bounded availability, Dispatch-window,
Timekeeping identity and Payroll identity.

## Source and current-work evidence

The admitted current-calendar baseline is 18 current/future Appointments across 15
Jobs. All 18 technician assertions use the current eight-identity provider roster;
current technician holds are zero. Historical evidence remains separate: 187
Appointments contain only roster-present technician IDs, while 292 historical
Appointments contain 452 assertions for 26 provider IDs absent from the current
roster. Those 292 remain source-backed/unassigned and are not certification evidence
for a current person.

For each owner decision, show the exact source ID, source display evidence, source
Branch/business-unit evidence, current/historical assignment counts, persisted ACP
candidate and evidence digest from the private packet. Never commit those private
records merely to populate a report.

## Owner acceptance

1. Open **Employees & Time → Real All County roster**.
2. For each source card with a persisted ACP target, inspect the private source
   packet and select the corresponding owner-confirmed roster identity.
3. Confirm the exact target. Do not use displayed-name or email similarity.
4. If no ACP target exists, use normal protected onboarding only after owner
   certification. Current onboarding cannot persist source lineage; record this as
   pending rather than claiming the crosswalk is complete.
5. Keep excluded system/non-employee evidence `LEGACY_ONLY`/`NOT_EMPLOYEE`.
6. Keep uncertain evidence on hold. No current schema-backed HOLD command exists in
   the roster workflow.
7. For each Field Technician, verify MAIN, both required roles, exact Mobile
   permissions and owner-certified `technician` capability. Record only a bounded
   real availability window.
8. For one exact real Appointment, run the acceptance script with its ID and require
   all five certified technicians expected for that window to report truthful
   eligibility. Assignment remains a separate human-confirmed Dispatch mutation.

## Mobile least privilege

`ACP_EMPLOYEE_MOBILE` grants exactly:

- `COMPANY_TIMEKEEPING_OWN_READ`
- `COMPANY_TIMEKEEPING_OWN_PUNCH`
- `COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ`
- `COMPANY_JOB_READ`
- `COMPANY_JOB_EXECUTE`

The companion `TECHNICIAN` role adds Customer read and Scheduling read alongside
the overlapping Job/My Day/own-time permissions. Neither role grants Payroll
administration, Accounting, payments, Price Book management or Company
administration. Pay-statement self-read, if later sanctioned, remains a separate
own-data permission and is not Payroll administration.

## Payroll identity handoff

Every roster person is either `IDENTITY_READY` or
`IDENTITY_CERTIFICATION_REQUIRED`. Only after identity is ready may Payroll report
the remaining categories: `COMPENSATION`, `TIME`, `W4`, `JURISDICTION`,
`DEDUCTIONS`, `YTD`, `BRIDGE_HISTORY`, and `ACCOUNTANT`. No value is exposed or
calculated by this packet.

## Post-integration acceptance

Use an authorized owner session stored in a mode-0600 file; never place the token on
the command line or in the report:

```bash
PYTHONPATH=backend python backend/scripts/real_workforce_cutover_acceptance.py \
  --base-url https://preview.allcountyhomeservices.com \
  --token-file /restricted/path/owner-token \
  --contract backend/operations/real-workforce-cutover-contract.v1.json \
  --appointment-id '<exact-real-preview-appointment-id>' \
  --output /restricted/path/real-workforce-result.json
```

The script fails closed per employee on missing binding, login, Membership, MAIN,
role, Mobile, technician capability, Timekeeping/Payroll identity, Appointment
eligibility, required role/permission, unexpected roster identity or field privilege
leakage. Omitting `--appointment-id` deliberately skips Appointment-window
eligibility; it must not be described as Dispatch acceptance.

## Minimal onboarding-lineage design — no migration yet

After #299/#311 integration, add one Company-scoped, versioned certification
aggregate rather than overloading invitation request keys:

- immutable key: `(company_id, source_system, source_employee_id)`;
- immutable source evidence reference/digest and source Branch reference;
- versioned decision: `CONFIRM`, `SELECT_EXISTING`, `CREATE_ONBOARD`, `HOLD`, or
  `LEGACY_ONLY`;
- optional resulting `employee_id` and `onboarding_request_id`, both Company-bound;
- actor, reason code, prior version, timestamp and audit correlation;
- one current version per source identity; append-only decision history;
- onboarding accepts a certification ID, never raw URL hints, and atomically attaches
  the resulting Employee to the certified source aggregate;
- no decision based on a name, email, phone or approximate match.

The implementation boundary is one model/migration, certification service/router,
optional onboarding certification reference, owner UI commands, audit events and
PostgreSQL tests for tenant isolation, immutability, concurrency, idempotency,
supersession, HOLD/LEGACY behavior and duplicate-Employee rejection.

## Owner packets

For Michael, Lianne and Alex, the owner confirms exact identity, ACP target, MAIN,
operating role and whether Mobile/Dispatch is not applicable. For each of Melvin,
Adam, Dareis, Dakota and Jason, the owner additionally confirms technician
classification, only known service capabilities, bounded availability and the exact
current Appointment used for Dispatch acceptance. Machine-known ACP IDs, source IDs,
roles and Branches are displayed; they are never retyped by the owner.

Employees establish their own password and authenticate. Apple/TestFlight enrollment
is external per employee and never blocks server-side certification.

# Payroll real roster and Timekeeping maximum 1

## Authority and safety boundary

- Starting protected authority: `b527d75eecb2d271a29bcb0bacb9e1b16b33784b`.
- Starting OM2E authority: `14f665e8683aa0b151d1bb46c1431962cadf2e3d`.
- The owner-confirmed All County operating roster contains eight people. The
  private Migration acceptance packet containing exact HCP Employee identifiers
  is not stored in Git and was not available to this worker.
- No Employee, User, Membership, source certification, time entry, compensation,
  Payroll input, Preview record, or Production record was created or changed.

## Exhaustive owner-confirmed roster ledger

| Person | Operating role | Current safe classification | Exact remaining evidence/action |
| --- | --- | --- | --- |
| Michael Fouse | Administrator | `SOURCE_CERTIFICATION_REQUIRED` | Owner must confirm the exact HCP identity and ACP Employee binding; period time/payroll applicability must then be reviewed. |
| Lianne Hernandez | Office Manager | `TIME_REQUIRED` | Existing canonical account/Employee/MAIN/role/Workforce evidence is reported ready. Exact source certification and truthful Sept. 5–11 accepted-time evidence remain required before Payroll readiness. |
| Alex Donahue | Office Staff | `ONBOARDING_REQUIRED` | Use the protected onboarding flow with the owner-supplied unique login email unless an exact existing ACP identity is independently proven. Never select Synthetic Beta Employee. Then certify the exact source identity and review time. |
| Melvin Santiago | Field Technician | `ONBOARDING_REQUIRED` | Exact Employee onboarding/binding is required unless independently proven. Then establish Workforce profile, Mobile roles, technician capability, bounded readiness, source certification, and accepted time. Never select Synthetic Beta Employee. |
| Adam Mari | Field Technician | `OWNER_INPUT_REQUIRED` | Owner must prove whether an exact ACP Employee already exists; otherwise use protected onboarding. Exact source identity, field readiness, and period time remain unproven. |
| Dareis Montgomery | Field Technician | `OWNER_INPUT_REQUIRED` | Owner must prove whether an exact ACP Employee already exists; otherwise use protected onboarding. Exact source identity, field readiness, and period time remain unproven. |
| Dakota Wilcox | Field Technician | `OWNER_INPUT_REQUIRED` | Owner must prove whether an exact ACP Employee already exists; otherwise use protected onboarding. Exact source identity, field readiness, and period time remain unproven. |
| Jason Calci | Field Technician | `OWNER_INPUT_REQUIRED` | Owner must prove whether an exact ACP Employee already exists; otherwise use protected onboarding. Exact source identity, field readiness, and period time remain unproven. |

These are conservative next-action classifications, not claims that absent
runtime evidence is false. No person is `READY` for Payroll from the evidence
available to OM2-C.

## Bounded product repairs

The real-roster card previously used the unqualified badge `Ready` when only its
identity/access blocker list was empty. It now says `Identity and access ready`,
shows the independent Timekeeping handoff, and keeps Payroll explicitly at
`LINKED INPUTS NOT EVALUATED` until Payroll evaluates the period inputs.

The Payroll period table now renders an Employee with zero accepted minutes and
`TIME_EVIDENCE_MISSING` as `No time entries`. A genuine query/service failure
continues to render the separate unavailable error. Zero evidence is no longer
presented as a service outage or as accepted payable time.

The previously reported Lianne access/capabilities/history dead link is already
protected at commit `45fe7b2f`: the canonical route is
`/employees?employee=<id>`. This candidate preserves that authority and does not
duplicate it.

## Source certification and time gates

Repository authority contains seven sealed HCP Employee identities and a
Company-scoped exact-ID certification workflow. Six historical rehearsal
candidates are not automatic live bindings. Names and email similarity are not
identity authority. OM2E/Migration must supply the private exact source packet to
an authorized owner session before any certification decision is made.

For September 5–11, Git contains no accepted real time evidence. Authorized
office staff must review each hourly Employee's actual punches/manual source,
correct exceptions through the governed Timekeeping workflow, and accept the
timecard. ACP must not create hours to fill the period. After acceptance, rerun
the exact-period Payroll readiness assembly; compensation, withholding,
jurisdiction, deductions, YTD, and accountant/provider gates remain independently
required.

## OM2E activation sequence

1. Deploy a coherent authority containing this UI candidate through the normal
   Release path.
2. Supply the private HCP Employee certification packet to an authorized owner;
   do not place provider identifiers in Git or general evidence.
3. Open **Employees & Time → Real employee activation** and process all eight
   roster cards. Select only an independently proven exact ACP Employee.
4. For an absent Employee, use protected onboarding with the owner-supplied
   unique email and the canonical operating profile. Do not create duplicates.
5. Complete exact HCP source certification for each applicable person.
6. Open the September 5–11 period. For every hourly Employee, review actual time;
   `No time entries` requires human entry/import of real evidence or an explicit
   exclusion decision, never generated hours.
7. Accept governed timecards, rerun Payroll readiness, and require every included
   Employee to have an empty blocker set before any separately authorized Payroll
   execution.

Payroll execution, payments, tax filing, Accounting posting, and money movement
remain outside this packet.

## Qualification

- Backend real-roster, source-certification, field-readiness, identity-onboarding,
  timecard/Payroll operations, and time-input integrity: 42 passed.
- Frontend real-roster, onboarding, Workforce, and Payroll: 18 passed.
- Focused frontend regression: 7 passed.
- ESLint: passed.
- TypeScript and production build: passed.
- PostgreSQL zero-to-head for the disposable test database: passed.
- No schema migration.

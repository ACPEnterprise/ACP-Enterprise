# Payroll real roster and Timekeeping readiness 1

## Authority and boundary

- Starting protected authority: `962dd8e24d48681655f1e6e8bd9a76e34b06a6f4`.
- Starting cumulative Operations authority: `704640776c895a120c1fe3a2d53b1c2144f6e0fe`.
- Payroll calculation and close remain owned by OM2-B under Issue #449.
- No Employee, User, Membership, roster binding, source certification, time entry,
  Payroll input, Preview record, or Production record was created or changed.

The roster contract contains the eight owner-confirmed people below. Repository
evidence does not contain the private source-identity packet, a sanctioned
authenticated Beta session, or an identified current pay period with real time
evidence. Therefore no person can truthfully be classified `READY`,
`TIME_ENTRY_REQUIRED`, `TIME_REVIEW_REQUIRED`, or `EXCLUDED_FROM_PERIOD` from
engineering evidence alone. Missing runtime evidence is not zero time.

## Owner queue

| Person | Approved operating role | Current classification | Exact next owner action |
| --- | --- | --- | --- |
| Michael Fouse | Administrator | `OWNER_CERTIFICATION_REQUIRED` | Select the exact canonical Employee and exact source identity; confirm employment status and whether the Employee belongs in the identified pay period. |
| Lianne Hernandez | Office Manager | `OWNER_CERTIFICATION_REQUIRED` | Open the existing canonical Employee through **Open access, capabilities and history**; confirm the source identity and employment/period inclusion. Then review the identified period for real entries. Do not create another Lianne. |
| Alex Donahue | Office Staff | `ONBOARDING_REQUIRED` | If no exact canonical Employee is proven, use **Create/onboard ACP Employee** with `OFFICE_STAFF`, MAIN, and the owner-supplied unique login email. Never select Synthetic Beta Employee. Then certify the exact source identity. |
| Melvin Santiago | Field Tech | `ONBOARDING_REQUIRED` | If no exact canonical Employee is proven, use **Create/onboard ACP Employee** with `FIELD_TECH`, MAIN, and the owner-supplied unique login email. Then verify Workforce/Mobile/technician readiness and certify the exact source identity. Never select Synthetic Beta Employee. |
| Adam Mari | Field Tech | `OWNER_CERTIFICATION_REQUIRED` | Determine whether an exact canonical Employee exists. Select it only with source evidence; otherwise use the canonical `FIELD_TECH` onboarding flow. |
| Dareis Montgomery | Field Tech | `OWNER_CERTIFICATION_REQUIRED` | Determine whether an exact canonical Employee exists. Select it only with source evidence; otherwise use the canonical `FIELD_TECH` onboarding flow. |
| Dakota Wilcox | Field Tech | `OWNER_CERTIFICATION_REQUIRED` | Determine whether an exact canonical Employee exists. Select it only with source evidence; otherwise use the canonical `FIELD_TECH` onboarding flow. |
| Jason Calci | Field Tech | `OWNER_CERTIFICATION_REQUIRED` | Determine whether an exact canonical Employee exists. Select it only with source evidence; otherwise use the canonical `FIELD_TECH` onboarding flow. |

After exact identity and period inclusion are established, the authorized office
reviewer must inspect each hourly Employee's real punches/import/manual evidence.
No entries is `NO TIME ENTRIES`; recorded or submitted entries require review;
only approved current revisions are accepted Payroll time. Corrections supersede
prior revisions and Payroll must consume a newly assembled evidence snapshot.

## Bounded engineering repair

The readiness projection previously collapsed employment into a generic
`EMPLOYEE_READY` or `EMPLOYEE_MISSING_OR_INACTIVE` state. It now returns and
renders the exact Company-scoped Employee status (`active`, `leave`, `inactive`,
or `terminated`) separately. This lets the owner make a truthful period-inclusion
decision without changing employment or Payroll authority.

The existing product already preserves:

- canonical `/employees?employee=<id>` access/capabilities/history navigation;
- separate identity/access, Workforce, Mobile, Dispatch, Timekeeping, and Payroll
  handoff labels;
- exact Company-scoped binding with duplicate-binding rejection;
- `OFFICE_STAFF` for Alex and `FIELD_TECH` for Melvin;
- sanctioned manual entry, submission, correction, approval, replay, audit, and
  immutable accepted-time evidence;
- `No time entries` separately from service failure.

## OM2E handoff

Integrate the bounded status projection, deploy through the normal Release path,
then have Michael or Lianne process the owner queue in Beta. Record the exact pay
period before reviewing time. For each included hourly Employee classify the
observed evidence as `TIME_ENTRY_REQUIRED`, `TIME_REVIEW_REQUIRED`, or `READY`;
explicitly classify genuine exclusions as `EXCLUDED_FROM_PERIOD`. Do not infer
those outcomes from the static roster.

Issue #449 remains an independent OM2-B gate. This packet neither implements nor
accepts Payroll calculation, close, payment, Accounting posting, or money movement.

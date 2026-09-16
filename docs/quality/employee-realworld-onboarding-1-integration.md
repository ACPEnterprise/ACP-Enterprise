# Employee real-world onboarding 1 — Enterprise handoff

## Authority and boundary

- Starting protected authority: `e9211fca8086c7fba333d8e5e2acaeaa191d56c2`.
- Owner-confirmed roster policy: Michael Fouse `ADMIN`; Lianne Hernandez
  `OFFICE_MANAGER`; Alex Donahue `OFFICE_STAFF`; Melvin Santiago, Adam Mari,
  Dareis Montgomery, Dakota Wilcox, and Jason Calci `FIELD_TECH`.
- The marketing/admin account is not part of this operational roster and remains
  owner-review-required.
- No HCP crosswalk is required for an owner-confirmed ACP-native onboarding, but
  an existing ACP identity must be selected through its exact login evidence; no
  name or contact similarity is authority.

## Product result

The ordinary Team / Employees onboarding route exposes exactly four operating
profiles:

| Owner choice | Canonical ACP roles | Result |
| --- | --- | --- |
| `ADMIN` | `COMPANY_ADMINISTRATOR` | Existing administrator boundary |
| `OFFICE_MANAGER` | `OFFICE_MANAGER` | Normal office/workforce/onboarding operations without owner hard gates |
| `OFFICE_STAFF` | `SERVICE_CSR` | Branch-scoped Customer and office read/manage authority already sanctioned by ACP |
| `FIELD_TECH` | `TECHNICIAN` + `ACP_EMPLOYEE_MOBILE` | Assigned work, own time, Job execution, and Mobile access without office/Payroll authority |

The Office Manager bundle includes normal Customer, Scheduling, Dispatch, Job,
Estimate, Invoice, payment visibility, Workforce, Employee onboarding/access,
Inventory, Purchasing, Communications, and Time review authority. It excludes
Company administration, role/permission administration, Price Book activation,
payment collection/application/refund, Accounting posting, and Payroll management.

`FIELD_TECH` does not itself assert availability. An authorized operator must use
the existing **Confirm field-ready for this appointment** action for the exact
Employee, MAIN Branch, and appointment window. That audited action establishes
the canonical `technician` capability and bounded availability atomically.
Office profiles never receive that capability automatically.

## Deployment and activation sequence

1. Integrate the candidate and apply Alembic head `m3n5p7r9t1v3`.
2. Confirm the Office Manager migration advances active affected users'
   authorization versions; Lianne must establish a refreshed session.
3. Sign in as the owner and open **Employees → Add Employee**.
4. For each roster person, first inspect the existing Team record. If an exact
   User/Membership/Employee already exists, administer that record; do not submit
   a duplicate onboarding request.
5. For each absent person, enter the owner-confirmed name, their owner-supplied
   unique login email, the profile above, and MAIN. Review the read-only plan,
   then send the protected invitation.
6. Record invitation, provider acceptance, delivery, activation, and login as
   distinct states. Do not copy activation secrets into evidence.
7. For each of the five Field Techs, open a real sanctioned appointment and use
   **Confirm field-ready for this appointment**, then refresh eligibility and
   assign only after it reports eligible.
8. Verify each activated Field Tech sees only assigned work and own Timekeeping.
   Verify Lianne has office operations and no technician capability.

Required owner inputs remain the exact unique login email for every person not
already bound to a proven ACP User. Phone is not required by the current protected
onboarding contract and must not be invented. Existing-identity conflicts stop for
review rather than creating a duplicate.

## Qualification

- PostgreSQL zero-to-head migration: passed; single head `m3n5p7r9t1v3`.
- Backend launch-role, identity-onboarding, and field-readiness suites: 43 passed.
- Frontend onboarding, Dispatch assignment, and Workforce suites: 9 passed.
- Focused Office Manager policy checks: 4 passed.
- ESLint, Ruff, MyPy, Python compilation, TypeScript, production build, and
  `git diff --check`: passed.

No real Employee record, credential, invitation, availability window, assignment,
Payroll/compensation value, HCP record, Customer communication, or Production state
was mutated by this lane.

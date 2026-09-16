# Workforce real Employee activation console 1 — Enterprise handoff

## Dependency and authority

- Starting protected authority: `bae55401586e48e4b606604c3aac1eeef4832a27`.
- Stack parent: PR #299 candidate
  `57852bdf20ed9e45a5dbaaad48540358b5c9dcf1`.
- Integration dependency: **REQUIRES PR #299**. Integrate #299 first; do not
  cherry-pick this candidate onto authority that lacks its roster binding model.
- No schema migration is added by this follow-on.

## Owner product

The Workforce page is now an eight-person activation console rather than a raw
technical roster. It provides a one-screen summary, `Needs action` and `Field
Tech` filters, and per-person evidence for ACP Employee, account, Membership,
MAIN Branch, operating role, Workforce profile, Mobile, Dispatch handoff,
Timekeeping identity, and Payroll identity.

Unbound entries require selection of one exact existing ACP Employee. The list
is explicitly not a candidate recommendation and performs no fuzzy matching.
`Not same person` clears the proposed selection; `Defer` is deliberately local to
the browser review and says that no identity decision was persisted. A durable
identity is created only by the existing audited exact-binding command.

If no exact Employee exists, `Create/onboard ACP Employee` opens the normal
sanctioned onboarding route with the owner-confirmed name, role profile, and MAIN
Branch prefilled. Login email remains empty and owner-required. The existing
plan-before-apply, duplicate conflict, invitation, reissue, revoke, activation,
and password-establishment contracts remain authoritative; no administrator
password is introduced.

## Bounded readiness and evidence

An authorized operator enters start, end, and a required reason once, then
records the window for an exact bound Field Tech. The backend continues to own
the atomic profile/technician-capability/availability command. The operator
reason is stored only in the Company-scoped immutable audit entry; generic roster
responses expose no audit payload. The console shows start, expiration, and safe
source for the currently active MAIN window.

The command remains idempotent for the exact Employee/Branch/window. Authorization
requires both capability and availability management. Branch access fails closed.
No permanent eligibility, assignment, or trade capability beyond the canonical
technician prerequisite is inferred.

## Role and downstream boundaries

The console explains the four durable operating profiles without adding grants:
Administrator, Office Manager, Office Staff, and Field Tech. ACP Employee Mobile
remains a composed role for Field Tech. Detailed access, role removal, capability,
language, availability, account disable/reactivation, password recovery, and
Employee evidence remain in the existing Employee detail workspace.

Payroll is a handoff only: the console reports identity linkage and links to the
authorized Payroll workspace. It never reads or displays compensation, W-4,
deduction, tax, or YTD values. The Dispatch consumer boundary is documented in
`docs/architecture/workforce/dispatch-readiness-handoff-v1.md`; this candidate
changes no Dispatch assignment implementation.

## Enterprise sequence

1. Integrate and deploy PR #299, including Alembic head `n4p6r8t0v2x4`.
2. Integrate this stacked candidate; it has no additional migration.
3. Sign in with Workforce capability and availability management authority.
4. Open Team / Employees and confirm the console reports eight roster entries.
5. For each unbound person, inspect existing Employees and select only an exact
   independently verified identity. Do not use the displayed name as evidence.
6. If no exact identity exists, use `Create/onboard ACP Employee`, enter the
   owner-supplied unique login email, review the plan, and send the invite.
7. Review account, invitation, Branch, roles, Mobile, Timekeeping, and Payroll
   identity independently.
8. For each of the five Field Techs, enter a bounded MAIN start/end and reason,
   record readiness, and confirm the displayed expiration.
9. Refresh Scheduling/Dispatch and confirm its existing eligibility response is
   true only for windows covered by the evidence. Dispatch must not create it.
10. Confirm expired, wrong-Branch, inactive, missing-role, or missing-capability
    cases remain unavailable with a reason.

No real identity, invitation, availability, role, Payroll value, assignment,
Preview state, or Production state was mutated by this development lane.

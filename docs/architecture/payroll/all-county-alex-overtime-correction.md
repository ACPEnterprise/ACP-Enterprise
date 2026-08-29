# All County Payroll v1.1 — Hourly Supervisor Overtime Correction

Status: owner-approved activation candidate; not persisted or activated.

All County Payroll Policy v1.1 supersedes the v1 activation candidate without
rewriting it. Effective August 29, 2026, the explicit `hourly_supervisor`
worker-class scope uses `straight_time_all_approved_hours`:

- every approved hour worked remains regular-rate payable;
- hours above 40 are not discarded or capped;
- no overtime premium is added;
- no zero multiplier is used;
- the Employee remains hourly.

The Company rule continues to apply outside that scope: a 2,400-minute weekly
threshold, 1.5 multiplier, and no daily overtime rule. Deterministic precedence
is Employee-scoped exception, then worker-class exception, then Company policy.
Multiple exceptions at the same specificity fail closed as conflicting.

Alex Donahue's approved non-monetary readiness is `hourly` with worker class
`hourly_supervisor`. His native Employee identity and actual hourly rate remain
unresolved. The exception cannot participate until protected runtime identity
and `payroll.compensation-authority.v1` evidence bind him to that class.

This policy does not assert a statutory exemption or legal classification.
Compliance eligibility remains separately reviewable, and the exception carries
an explicit compliance-review requirement.

No wage amount, monetary Payroll calculation, identity mutation, or runtime
activation is contained here.

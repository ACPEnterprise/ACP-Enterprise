# Workforce and Technician Operations program

## Authority classification

| Capability | State | Authority |
| --- | --- | --- |
| Employee operational identity | COMPLETE | Platform Employee and Company Membership |
| Capability profiles | COMPLETE | Workforce capability persistence |
| Languages | COMPLETE | Explicit Workforce language evidence |
| Certifications | COMPLETE | Workforce credential evidence; no legal-validity inference |
| Branch eligibility | COMPLETE | Effective Workforce Branch eligibility |
| Working availability | PARTIAL | Explicit windows exist; Production policy remains unconfigured |
| Assignment eligibility | COMPLETE | Read-only Workforce eligibility service |
| Crew composition | PARTIAL | Dispatch assignment crew evidence exists; persistent named-team policy is absent |
| Training programs | POLICY_GATE | No approved required-training catalog |
| Performance ranking | POLICY_GATE | Operational facts exist; subjective scoring is prohibited |
| Payroll composition | EXTERNAL_GATE | Payroll remains separate and protected |
| Employee Mobile | COMPLETE | Existing own-day and field contracts; no admin authority added |
| Fleet | MISSING | Deferred fallback; maintenance policy and asset authority are absent |

## Product boundary

The Workforce workspace exposes Company- and Branch-scoped operational identity,
explicit capabilities, languages, credentials, equipment capability, restrictions,
and deterministic readiness blockers. It exposes no compensation, tax, deduction,
banking, net-pay, or Payroll configuration material.

Eligibility is advisory evidence for Scheduling and Dispatch. It never assigns an
Appointment, changes Dispatch state, chooses a technician, or mutates field work.
Unknown working hours, credential requirements, training requirements, and crew
policy remain unconfigured rather than guessed.

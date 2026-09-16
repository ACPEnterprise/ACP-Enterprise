# Workforce → Dispatch readiness handoff v1

Workforce owns Employee identity, Company and Branch scope, capability evidence,
and bounded working availability. Dispatch is a read-only consumer of that
authority when deciding whether an Employee may be selected for an appointment.

For an exact appointment window, Dispatch may consume:

- `employee_id` and display name;
- Company and Branch scope;
- `eligible` (`true` or `false`);
- stable reason codes when eligibility is false;
- active capability codes required by the appointment;
- availability confidence and the evaluated bounded time window.

An availability end time is the readiness expiration. A past or non-covering
window cannot be treated as eligible. Missing evidence is not `false` evidence of
skill and is never promoted by the assignment panel.

Dispatch must not create or modify a Workforce profile, role, capability,
certification, language, Branch grant, or availability record. Authorized owners
perform those commands in Workforce before Dispatch refreshes its existing
eligible-technicians projection. Assignment remains a separate Dispatch command.


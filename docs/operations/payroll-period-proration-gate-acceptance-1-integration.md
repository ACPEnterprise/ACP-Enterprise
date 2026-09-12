# PAYROLL.PERIOD.PRORATION.GATE.ACCEPTANCE.1

This stacked successor repairs a demonstrated period-assembly gap. Compensation
authority is now resolved at both inclusive pay-period boundaries. If the
approved authority identity or digest changes inside the period, assembly fails
closed with `mid-period compensation change requires proration policy`.

The predecessor remains immutable and historically resolvable; no effective
date or digest is rewritten. This change does not invent a proration rule,
calculate taxes, execute Payroll, post Accounting, or move money.

Qualification uses synthetic PostgreSQL compensation and period evidence only.

# WORKFORCE.TIME.PAYROLL.CORRECTION.INTEGRITY.1

This stacked successor closes a Payroll operations projection ambiguity found
after `WORKFORCE.TIME.PAYROLL.INPUT.INTEGRITY.1` was handed off.

The Payroll period workspace now recognizes only a current Workday revision in
the `approved` state as accepted time. An inherited or historical approval
timestamp cannot make a `corrected`, `submitted`, or `recorded` successor
payable. This keeps operating totals, snapshot-staleness evaluation, and the
Payroll sealing contract aligned after corrections.

The candidate adds no migration and performs no Payroll execution, Accounting
posting, payment, Preview deployment, or Production mutation.

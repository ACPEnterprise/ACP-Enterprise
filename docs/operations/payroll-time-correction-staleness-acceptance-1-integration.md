# PAYROLL.TIME.CORRECTION.STALENESS.ACCEPTANCE.1

This stacked acceptance successor proves that an accepted Workday correction
immediately makes the previously sealed Payroll Time Input stale. Downstream
gross-pay persistence/review cannot continue from the old snapshot. After the
corrected successor is submitted, approved, and sealed, the new snapshot is
current and has a distinct digest.

The test uses synthetic PostgreSQL evidence only. It adds no calculation or
withholding policy and performs no Payroll execution, posting, payment, Preview,
or Production operation.

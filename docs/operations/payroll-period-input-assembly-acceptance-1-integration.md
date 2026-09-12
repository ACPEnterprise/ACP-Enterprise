# PAYROLL.PERIOD.INPUT.ASSEMBLY.ACCEPTANCE.1

## Dependency and authority

This acceptance candidate began from protected authority
`d52d117801d72d04e81afac157671c97a941efa0` and composes the exact unmodified
PR #221/#222/#225/#226 stack. Integrate it after #226.

## Accepted assembly contract

The PostgreSQL-backed suite proves that Payroll admission binds one sealed
Workday snapshot and one approved effective compensation authority by their
immutable identities and digests. Resolution is deterministic at the period
effective date:

- a historical compensation revision remains resolvable before its successor's
  effective date;
- the approved successor is the sole resolution on and after its effective date;
- an overlapping competing compensation authority fails closed;
- missing compensation blocks assembly without altering time evidence;
- Company/Employee mismatch produces a conflicting admission packet;
- branch remains Workday source evidence rather than a Payroll reassignment;
  cross-branch work is not silently rewritten to the Employee home branch;
- tax-election evidence is not an input to this admission packet and its absence
  does not mutate time; tax readiness remains a downstream gate; and
- replay produces the same admission digest.

Workday service selection uses inclusive `work_date` period bounds. Evidence
outside the period is excluded, and mid-period policy or compensation changes
are rejected by gross-input validation pending an explicit proration policy;
they are never duplicated or silently split.

The correction-staleness acceptance inherited from #226 proves a correction
invalidates the prior sealed snapshot and resealing creates a new current digest.

No tax calculation, Payroll execution, Accounting posting, payment, Preview, or
Production operation is performed. All evidence is synthetic.

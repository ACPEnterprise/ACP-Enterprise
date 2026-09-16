# LIA Payroll Readiness Guidance 1

Starting protected authority: `90af57abf5f4e2dbda75ed2680d4d420eb60410c`.

## Defect

The existing read-only Payroll adapter correctly returned Employee readiness
blocker codes, but the generic LIA response formatter rendered the same internal
state list for readiness, explanation, and next-action questions. It did not
interpret responsibility or the dependencies already enforced by Payroll
operations.

## Bounded interpretation

The deterministic interpreter recognizes these existing authoritative blockers:

- `COMPENSATION_MISSING_CONFIGURATION`: owner establishes approved compensation
  basis, rate or salary, effective date, and overtime applicability.
- `PAYROLL_POLICY_MISSING_CONFIGURATION`: owner completes one effective approved
  Company Payroll policy, obtaining accountant certification where the protected
  Payroll setup identifies a tax or jurisdiction decision.
- `TIME_EVIDENCE_MISSING`: actual time evidence must be entered/imported,
  exceptions resolved, and the pay-period snapshot approved.
- `GROSS_PAY_NOT_CALCULATED`: ACP calculation after compensation, policy, and
  accepted time prerequisites.
- `WITHHOLDING_NOT_CALCULATED`: ACP calculation after gross pay and approved W-4
  and work/residence jurisdiction authority.

Answers distinguish readiness, blocker explanation, ordered next actions,
owner-completable work, accountant evidence, and what ACP calculates afterward.
The interpreter does not infer that W-4 or jurisdiction evidence is missing; it
directs the owner to verify it and obtain/certify it only when absent.

## Safety and qualification

- Existing Payroll retrieval, permissions, evidence digests, and Employee
  referent continuation are unchanged.
- No protected compensation amount, tax election, banking value, or Payroll
  input is rendered.
- No action proposal or mutation path is added.
- Focused guidance/continuation: 23 passed before final ordering refinement; the
  final guidance suite: 5 passed.
- Broader LIA and affected Payroll suites: 95 passed against fresh PostgreSQL.
- Ruff, MyPy, Python compilation, fresh migration to existing head, diff, and
  leakage checks passed.
- No migration or schema change.

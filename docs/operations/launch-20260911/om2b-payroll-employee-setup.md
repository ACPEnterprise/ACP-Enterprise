# OM2-B Payroll Employee setup checkpoint

- Mission: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Starting authority: `2d8709c895e60faf7cc0251d6c8ac82311013613`
- Branch: `work/payroll-employee-setup-operations-1`
- Worktree: `ACP-Enterprise-OM2B-payroll-setup`

## Implemented

Employee → Pay navigation now opens an operator setup workspace. It reads the
existing Company-scoped compensation and tax/deduction authority histories,
shows the latest admitted `READY_FOR_PAYROLL` or `BLOCKED_FOR_PAYROLL` state and
exact safe blockers, and creates effective-dated drafts without Employee UUID
entry. Separate authorized approval preserves the existing drafter/approver
separation and supersession history.

Supported setup evidence includes hourly/salary authority, effective date,
salary frequency, classification reference, federal W-4 filing status and Steps
2/3/4, tax jurisdiction, state/local elections, pre/post-tax deductions, and YTD
Social Security/Medicare wage evidence. Confidential values are encrypted by
the existing protected Payroll-input envelope; they never return through the
read API. If the environment-specific keyring is absent, writes requiring
protected values fail closed and the UI explains the exact configuration gate.

## Authoritative limitation

The current protected Payroll calculation engine is component-neutral. It does
not contain an admitted jurisdiction-specific federal W-4/IRS table provider or
rules for single, married filing jointly, head of household, Steps 2–4, Social
Security wage-base crossing, Medicare, or Additional Medicare thresholds.
Those independent calculation cases therefore remain `SOURCE_REQUIRED`; no tax
formula or threshold was invented in this lane. Existing deterministic generic
tax/deduction calculation tests remain authoritative.

## Enterprise integration

1. Integrate the candidate on a descendant of the recorded authority.
2. Configure `PAYROLL_INPUT_ENCRYPTION_KEYS` as a secret JSON keyring of
   URL-safe-base64 32-byte keys and select `PAYROLL_INPUT_ACTIVE_KID`; do not put
   keys in Git, frontend configuration, or logs.
3. Deploy coherently to Preview and verify the setup routes require the existing
   compensation/tax/deduction permissions.
4. Using sanctioned synthetic Employees, have one authorized operator draft and
   a different authorized operator approve a compensation and protected input
   successor. Confirm prior versions remain visible and unchanged.
5. Reassemble/re-evaluate the Payroll run through existing authority and verify
   exact blockers clear only when all admitted requirements are satisfied.

No migration is required. No Payroll transmission, filing/payment, Accounting
posting, money movement, QBO mutation, Preview deployment, or Production action
is authorized from this lane.

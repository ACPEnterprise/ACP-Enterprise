# OM2-B Payroll and Accounting continuation

- Mission commit: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Base authority: `b22297c65165280a761860198dc05441df4a4312`
- Branch: `work/om2b-payroll-accounting-continuation-1`
- Status: IMPLEMENTED; qualification in progress

## Current work

The Payroll operating register now exposes its existing component-level tax,
deduction, employer-liability, compensation-authority, tax-rule, and Job labor
evidence. Missing evidence remains unavailable. The QBO consumer now validates
the protected `qbo-accounting-evidence/v1` contract, explicit basis, sealed
current authorization, historical staleness, amount availability, and
multi-source conflict evidence before rendering.

## Remaining checks

Run the complete frontend suite and affected backend QBO/Payroll/Timekeeping
tests, reconcile any protected movement, push the candidate, and provide the
Enterprise integration/deployed-acceptance packet.

## External gates

Real-company QBO acceptance still requires sanctioned authorization and a
coherent Enterprise Preview deployment. Real Payroll acceptance requires actual
approved compensation, elections, deductions, jurisdictions, prior/YTD wages,
and pay-period configuration; no values are inferred.

No QBO mutation, Payroll transmission, tax filing/payment, Accounting posting,
money movement, Preview deployment, Production, or Customer communication.

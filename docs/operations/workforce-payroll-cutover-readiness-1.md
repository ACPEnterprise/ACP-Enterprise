# Workforce and Payroll cutover readiness

Authority date: 2026-10-06. This packet records owner-authorized population and
machine-verifiable requirements; it does not certify deployed ACP data.

## Owner-authorized population

The active roster is Michael Fouse (Owner), Lianne Hernandez (Operations
Manager), Alex Donahue (Field Service Manager), Melvin Santiago (Technician),
Jason Calci (Technician), Dakota Wilcox (Technician), and Malcolm Calci
(Helper). Dareis and Kamen are terminated historical Employees. Neither belongs
in active roster onboarding.

The protected read-only acceptance command remains:

```text
python -m scripts.real_workforce_cutover_acceptance \
  --base-url <beta-api> \
  --token-file <sanctioned-owner-token-file> \
  --contract operations/real-workforce-cutover-contract.v1.json \
  --output <evidence-output.json>
```

Run it only with a sanctioned token. It sends no invitation and performs no
mutation. Until a fresh result is captured, invitation acceptance, login,
Membership, MAIN Branch, Mobile, timekeeping, and Dispatch readiness remain
unverified rather than assumed.

## QuickBooks Payroll evidence required

QBO accounting acquisition is not evidence that detailed QuickBooks Payroll
history was acquired. The sealed source package must contain, where available:

- payroll register and paycheck detail by Employee and pay run;
- pay-period dates and pay date;
- regular/overtime hours and wages, other earnings, reimbursements;
- employee and employer taxes, deductions, and contributions;
- net pay, payment method, check/direct-deposit identity, and check number;
- liability, remittance, and settlement evidence;
- Employee-level YTD wages, taxes, deductions, contributions, and net;
- provider IDs, versions, cutoff/as-of, manifest, and immutable digests.

Exact QBO identity must bind to an ACP Employee as `EXACT`,
`OWNER_CONFIRMATION_REQUIRED`, `UNRESOLVED`, or `HISTORICAL_TERMINATED`. Names
alone are not binding evidence.

## Physical bridge queue for Lianne

Do not assume that “approximately four weeks” identifies dates or population.
For every physical pay stub/check register entry, create the exact bridge period
and record the Employee, period start/end, pay date, gross wages, regular
hours/wages, overtime hours/wages, other earnings, deductions, employee taxes,
employer taxes, reimbursements, net check, check/reference number, liability
impact, payment status, tax/remittance status, source document reference, and
notes. Values remain encrypted protected facts and require owner/accountant
certification according to the canonical cutover policy.

Bring or securely reference:

- the four-week pay stubs and payroll/check registers;
- accepted timecards or other authoritative hours evidence;
- front/back check evidence or bank evidence for each paid paper check;
- tax and liability worksheets plus remittance confirmations;
- Employee deduction/contribution detail;
- the final QuickBooks Payroll YTD report at the exact cutoff;
- any correction, void, reversal, or off-cycle payment evidence.

ACP must not derive missing values from bank amounts or current Employee setup.

## Dareis and Kamen final paper checks

Each is expected to have two future final paper checks. Do not create or issue
them as part of cutover evidence capture. After an authorized external Payroll
calculation and physical issuance, an authorized cutover operator can record
the same bridge fields against the inactive/terminated Employee. The cutover
path does not activate a User, Membership, Mobile, Dispatch, or employment
status. Normal active-Employee paper-check execution remains intentionally
unavailable to terminated Employees.

## YTD and Accounting completion

Employee YTD is reconcilable only when detailed QBO source history, every bridge
period, and later final-check evidence share an exact Employee identity and
cutoff. For each Employee retain source YTD, ACP YTD, bridge-required state,
difference, and certification state. Missing or unexplained differences never
become zero.

Accountant Close additionally requires approved Payroll runs, approved account
mappings, posted journal/GL lines, liabilities and settlements/remittances,
opening/YTD certification, exact Employee identity, cutoff, and source lineage.
This packet neither posts Accounting nor certifies those requirements.

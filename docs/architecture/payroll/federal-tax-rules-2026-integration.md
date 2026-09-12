# Federal Payroll tax rules 2026 integration

## Authority and boundary

This candidate supplies the missing effective-dated 2026 calculation provider
to the existing Payroll engine. It does not create employee elections, approve
Payroll, transmit Payroll, file or pay taxes, post Accounting, or move money.
An Employee without complete admitted W-4, jurisdiction, YTD, compensation, and
time evidence remains `BLOCKED_FOR_PAYROLL` under the existing readiness contract.

## Official source manifest

| Rule | Authority and version | Effective interval | Reference | SHA-256 |
| --- | --- | --- | --- | --- |
| Federal income-tax withholding | IRS Publication 15-T (2026), automated percentage method | 2026-01-01 through 2026-12-31 | `https://www.irs.gov/pub/irs-prior/p15t--2026.pdf` | `31b3e2428628e8d2e40f6266c2c8f1b9b0b6ccd24607895f9b3be3d9d306d3fb` |
| Social Security, Medicare, Additional Medicare | IRS Publication 15 (2026), Circular E | 2026-01-01 through 2026-12-31 | `https://www.irs.gov/pub/irs-prior/p15--2026.pdf` | `b46c3622439d8521e3a0faca4cd5b5ece3451b526f65f06a5e38d5c9f804c88b` |
| Social Security taxable maximum cross-check | Social Security Administration, Contribution and Benefit Base, 2026 | Calendar 2026 | `https://www.ssa.gov/oact/COLA/cbb.html` | Live official reference; IRS Publication 15 digest is the executable rule-pack digest |
| Florida individual income-tax applicability | Florida Department of Revenue FAQ ID 1466 | Revalidate for each rule year | `https://floridarevenue.com/faq/Pages/FAQDetails.aspx?FAQID=1466` | `842a381379c6bfcce4ef753ce52651702c17510ace35885dee86e8b60ff65bd8` |

Calculation method version is
`irs-2026-percentage-method-automated.v1`. Currency results use deterministic
minor-unit half-up rounding. The evidence digest binds the rule source metadata,
source digest, complete protected-input digest, public calculation context, and
result.

## Supported calculation

- 2020-or-later W-4 filing status, Step 2 checkbox, Step 3 credits, Step 4(a)
  other income, Step 4(b) deductions, and Step 4(c) additional withholding;
- IRS automated percentage method for weekly, biweekly, semimonthly, monthly,
  quarterly, semiannual, and annual pay;
- employee and employer Social Security at 6.2%, limited by the 2026 $184,500
  annual wage base using admitted YTD wages;
- employee and employer Medicare at 1.45%, without a wage limit;
- employee-only Additional Medicare at 0.9% on employer-paid wages over the
  $200,000 calendar-year withholding threshold, including within-period crossing;
- separately supplied federal and FICA pre-tax wage adjustments; and
- explicit Florida work-and-residence evidence yielding state withholding
  `NOT_APPLICABLE`. Any other or incomplete jurisdiction is rejected for a
  separate effective-dated provider.

## Independent qualification cases

Reference expectations are calculated directly from IRS Worksheet 1A and its
published annual tables, not from ACP output: single biweekly; married filing
jointly with Step 2; head of household with Steps 3/4(a)/4(b)/4(c); Social
Security wage-base crossing; Additional Medicare threshold crossing; both FICA
shares; missing protected election evidence; effective-date rejection; and
Florida jurisdiction rejection.

## Enterprise reconciliation

Integrate this candidate with the then-current protected authority and PR #223's
Employee setup candidate. Keep protected W-4 values inside their existing
envelope authority; construct this provider only after admission resolves every
required input. Run the Payroll suite and an authorized, read-only readiness
reconciliation after deployment. Real Employee calculation acceptance remains
blocked until protected setup is deployed and complete; no real calculation was
claimed here.

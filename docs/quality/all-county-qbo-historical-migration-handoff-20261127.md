# All County QBO historical migration handoff

Status: integration candidate; protected deployment and owner acceptance are not authorized here.

## Isolated authority

- Company: `All County Plumbing & Leak — Accounting Migration`
- Company code: `ALLCOUNTY-QBO-HISTORY`
- Owner activation identity: `mifo66@gmail.com`
- Source cutoff: `2026-11-19`
- Accounting basis: cash
- Currency: USD
- QBO mutation authority: none
- Native posting authority: none

The historical routes require both the normal authenticated Accounting permission and the
exact isolated company code. They cannot fall through to live QBO acquisition. The custody
package is mounted read-only and its complete manifest is verified before each projection.

## Source population and controls

- Surviving API acquisition control: 20,702 records and 97,093 relationship identities.
- Original bounded snapshot digest recorded by two surviving controls:
  `e4d672c1cdfca858e4a8e923a51a86627753c7ea1fedc695daa98066a5dc6041`.
- Searchable sealed source reports: 21/21 files verified.
- General Ledger: 46,405 dated rows, 2021-07-07 through 2026-11-19,
  total amount control `$7,496,709.24`.
- Transaction Detail: 46,410 rows; the five-row presentation difference is `$0.00`.
- Accounts: 131; Customers: 909; Vendors: 868; Invoices: 1,341;
  historical paychecks: 709.
- Trial Balance: `$2,021,520.50` debits and credits, difference `$0.00`.
- Balance Sheet: `$730,223.61` assets and liabilities plus equity, difference `$0.00`.
- 2026 P&L net income: `$373,644.93`, provider difference `$0.00`.
- Source P&L, Balance Sheet, Trial Balance, General Ledger, cash activity, bank/card
  activity, directories, invoices, and payroll history are exposed read-only in the
  authenticated Financial Reports workspace.

Historical rows use deterministic custody-file/row identities. These are evidence identities,
not QBO provider record IDs. The missing provider envelope store is not represented as present.
Attachments were not included in the preserved exports. Detailed payroll API records were not
available under the accounting OAuth scope.

## Exceptions

All seven disclosed conflicts remain visible and unmodified. The review workbook is outside Git:

`/Users/michaelbfouse/ReleaseEvidence/qbo-historical-migration-20261127/AllCounty_QBO_Historical_Exceptions.xlsx`

Workbook SHA-256:
`e8e152272b131864fb264a9223e9c7a3020f6bd0072cfb08a1e1d889ed9f7d85`

No disposition is preapproved. In particular, the `$100,801.91` A/R bridge, 73 unlinked
payments totaling `$85,414.91`, provider unapplied amount `$87,544.91`, 102 unposted AmEx
rows, four repeated AmEx rows, and payroll coverage differences remain held for owner/Finance
review.

## Activation and acceptance boundary

Laptop Master must integrate the candidate, provision the isolated company through the supported
bootstrap, and use the secure password setup/reset workflow for the owner. No password or reset
token belongs in this handoff. Owner acceptance requires a fresh authenticated browser session,
review of all reports and drill-downs, and explicit disposition of each exception. This branch
does not authorize Beta or Production deployment.

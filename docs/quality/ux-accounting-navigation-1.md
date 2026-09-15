# UX Accounting Navigation 1

## Authority and scope

- Starting protected authority: `7f1d98dc68016dc55e8454fb009d319aa4ee6396`
- Frontend information architecture only; no financial domain behavior, source
  authority, permission, calculation, posting, payment, Payroll, or QBO mutation
  was changed.

## Route reconciliation

| Accounting task | Route | Classification | Navigation treatment |
|---|---|---|---|
| Overview | `/accounting` | `EXISTING_ROUTE_RENAME_ONLY` after this bounded shell was added | Permission-filtered links to real surfaces only |
| Financial Reports | `/financial-reports` | `EXISTING_ROUTE` | Accounting |
| Chart of Accounts | — | `NOT_YET_IMPLEMENTED` | Omitted; no fake page |
| General Ledger / Journal Entries | `/financial-reports` | `CROSS_LINK_REQUIRED` | General Ledger remains an existing report option; no standalone route claimed |
| Accounts Receivable | `/invoices` | `EXISTING_ROUTE_RENAME_ONLY` | Accounting label; original route and deep links preserved |
| Accounts Payable | `/accounts-payable` | `EXISTING_ROUTE` | Accounting |
| Bank & Card Reconciliation | — | `NOT_YET_IMPLEMENTED` | Omitted |
| Undeposited Funds | — | `NOT_YET_IMPLEMENTED` | Omitted |
| Payroll Accounting | `/payroll` | `EXISTING_ROUTE_RENAME_ONLY` | Accounting label; existing Payroll route preserved |
| QBO Source Evidence / Reconciliation | `/financial-reports` | `CROSS_LINK_REQUIRED` | Existing QBO evidence remains within Financial Reports |
| Close / Period Controls | — | `NOT_YET_IMPLEMENTED` | Omitted |
| Payment/receipt evidence | `/payments` | `EXISTING_ROUTE_RENAME_ONLY` | Accounting label; existing route preserved |

## Intentionally retained operational navigation

- Revenue Cycle remains in Operations and continues linking to Estimates,
  Invoices, and Payments.
- Purchasing remains in Operations; it is not presented as the Accounts Payable
  implementation.
- Existing Invoice, Payment, Payroll, AP, and Financial Report URLs remain
  unchanged, preserving bookmarks and cross-domain links.

## Permission and responsive behavior

The Accounting overview appears only when the user has at least one supported
Accounting read permission. Each destination is independently filtered by its
existing permission. The existing desktop collapse and mobile drawer behavior
is reused; no additional nested expansion is introduced on narrow screens.

## Qualification

- Focused navigation and landing tests: 11 passed.
- Complete frontend suite: 479 passed across 126 files.
- ESLint: passed.
- TypeScript project build: passed.
- Production Vite build: passed.
- `git diff --check`: passed.
- Screenshots: not captured; no configured browser screenshot harness was
  required for this bounded navigation change.

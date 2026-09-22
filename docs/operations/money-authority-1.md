# MONEY.AUTHORITY.1

## Protected authority audited

Protected authority already owns provider-neutral Payment intents, attempts,
captured receipts, applications, refunds, disputes, provider settlements,
deposit preparation, reconciliation exceptions, Accounting posting receipts,
and immutable Business Events. Invoice authority owns contractual due dates,
terms, remaining open balance, customer/job linkage, and the Command Center AR
aging buckets introduced by PR #482.

The Money projection reuses those records. It does not introduce another
ledger, payment state machine, Invoice balance, or Accounting posting model.

## Read-only projection

`GET /api/v1/payments/money-position` requires an explicit period and `as_of`
date and remains protected by `payment.read`. Optional Branch scope is checked
against the caller's authorized Branch set.

The response keeps these facts separate:

- captured provider receipts plus separately labeled office-observed manual
  payment evidence (`collected`), while card amount charged remains provider
  receipts only;
- provider payout evidence (`settled_gross`, actual fees, and `settled_net`);
- bank-confirmed deposits (`UNAVAILABLE` in current authority);
- actual external bank balance (`NOT_CONNECTED` / `UNAVAILABLE`);
- exact open Invoice balances contractually due on the `as_of` date;
- scheduled COD expectation (`UNAVAILABLE` until structured terms and truthful
  scheduled-value evidence exist).

Expected Collections Today is therefore `INCOMPLETE` even when AR due today is
available. Missing COD evidence never becomes zero. Scheduled work under NET
terms is not classified as expected cash today; the corresponding Invoice
enters the projection only on its contractual due date.

## Evidence and drill-down

Card transaction rows bind receipt, intent, Branch, Customer, optional Invoice,
provider operation, captured/refunded/disputed amounts, capture timestamp, and
evidence digest. Actual fee evidence binds provider payout, settlement date,
gross, fee, net, reconciliation state, and digest. Current schema does not
allocate payout fees to individual charges, so the projection says so.

AR due today returns the exact Invoice population and the canonical Command
Center drill-down filter. Remaining open balance prevents partially paid
Invoices from being double-counted.

## External gates

1. A structured Company/Customer payment-terms authority and sanctioned
   scheduled-value basis are required for COD forecasting.
2. Provider transaction-to-payout allocation is required for per-charge fee and
   settlement attribution.
3. Provider/bank confirmation with a deposit timestamp is required before a
   prepared deposit can be called deposited.
4. A sanctioned bank connector is required for current/available balance and
   provider-as-of evidence.

No source system, Customer, Invoice, payment, Accounting journal, bank, Preview,
or Production state is mutated by this projection.

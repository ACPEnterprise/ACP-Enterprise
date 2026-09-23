# Money Payment Terms and COD Authority

## Authority

Expected Collections Today composes two distinct, evidence-backed populations:

1. scheduled Jobs occurring on the selected business date whose approved
   Company or Customer payment-term policy is `COD` or
   `DUE_ON_COMPLETION`, and whose value is proven by the immutable accepted
   Estimate revision converted to that Job; and
2. issued, partially paid, or adjusted Invoices whose authoritative due date is
   exactly the selected date, using only the remaining open balance.

Overdue Invoices are not included in due-today. Scheduled work under `NET`
terms is not treated as expected cash today. `DUE_ON_RECEIPT` is represented
explicitly but does not make un-invoiced scheduled work collectible today.

## Payment-term evidence

`payment_term_policies` is versioned, Company-scoped authority. A policy may be
a Company default or a Customer-specific override. Each version preserves its
effective window, source identity, evidence digest, approval actor, and
idempotent command identity. Resolution uses the effective Customer policy
first, then the effective Company default. Free-text Invoice or Estimate terms
are never parsed into authority.

If a scheduled Job has no effective approved policy, or no accepted Estimate
revision proving its value, the COD component is `INCOMPLETE` and its aggregate
amount is unavailable. It is never reported as zero. Mixed currencies likewise
remain unavailable through the existing Money projection rules.

## Stored-card boundary

The provider-neutral contract permits only opaque payment-method tokens,
processor Customer references, brand, last four digits, expiry metadata, an
authorization reference, and evidence digests. It also distinguishes
card-present from card-not-present transactions and preserves separate
settlement and deposit references.

Raw PAN, CVV/CVC, security codes, provider credentials, and processor-specific
runtime behavior are outside ACP authority and must never enter these contracts.
No processor is selected or integrated by this milestone.

## Remaining external dependencies

- A separately admitted processor is required for card authorization,
  settlement, fee, and deposit evidence.
- Bank balance remains unavailable until a sanctioned bank-data source exists.
- Company and Customer payment-term policies must be admitted from exact
  approved contractual evidence; missing policy stays incomplete.
- Scheduled COD value requires an accepted Estimate-to-Job conversion. Other
  scheduled-value sources require a separately accepted domain contract.

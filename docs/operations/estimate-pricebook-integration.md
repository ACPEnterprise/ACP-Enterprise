# Estimate / Price Book integration

## Operator contract

Estimate operators select a Customer, Branch, effective date, and one or more
eligible Price Book services. The effective catalog is restricted to active
service items and exactly one active Price Book version whose effective window
contains the requested time. Branch-specific pricing takes precedence over
Company-wide pricing. Missing or ambiguous authority is omitted from discovery
and rejected again during snapshot creation.

Search covers the service name, code, and customer-facing description. Category,
tax treatment, sell price, and active option constraints are returned. Internal
descriptions, component costs, and management-only Price Book operations are not
part of this contract.

Selecting a service calls the Estimate-specific snapshot endpoint. It requires
both `COMPANY_ESTIMATE_MANAGE` and `COMPANY_PRICE_BOOK_READ`; it does not grant
`COMPANY_PRICE_BOOK_MANAGE` or `COMPANY_PRICE_BOOK_ACTIVATE`. Historical selection
is prohibited on this endpoint. The authoritative Price Book snapshot service
re-resolves effective authority inside its transaction, validates options, and
writes the existing immutable commercial snapshot and audit evidence.

Estimate creation continues to consume snapshot identities through the existing
Estimate domain service. Quantity, sell price, extended amount, currency, tax
classification, selected option labels/constraints, effective time, version
identity, and digest are frozen. Activating a later Price Book version cannot
change an existing Estimate revision.

## Enterprise protected qualification

No schema change is introduced. Protected PostgreSQL qualification must run:

```text
ENVIRONMENT=test PYTHONPATH=. pytest -q \
  tests/price_book/test_price_book_service.py \
  tests/estimates/test_estimate_foundation.py \
  tests/price_book/test_price_book_api.py
```

This must include effective/future filtering, Branch precedence, superseded and
inactive rejection, immutable snapshot replay, Company/Branch isolation, option
validation, tax evidence, and dual-permission denial. Then run the repository's
fresh zero-to-head, one-head, current=head, and zero-drift gates even though this
candidate adds no migration.

The candidate is intentionally independent of the earlier Price Book operator
readiness branch. Enterprise should integrate that candidate first or reconcile
the two bounded frontend Price Book API/type surfaces without changing snapshot
or permission semantics.

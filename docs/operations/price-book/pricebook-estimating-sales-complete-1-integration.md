# PRICEBOOK.ESTIMATING.SALES.COMPLETE.1 integration packet

## Authority and composition

This successor started from protected authority
`481ada5dddc7586163bf650556abecc66269a655` and reconciles, rather than
recreates, the useful work in PR #290 (`PRICEBOOK.REALWORLD.COMPLETE.1`). The
Price Book review migration is rebased onto protected head `n4p6r8t0v2x4`; the
candidate head is `n0p8q16g3t9u`.

No real All County price is activated by this candidate. HCP remains reference
evidence only. Existing All County candidate counts and provenance remain intact.

## Operating capability

- Nested, ordered categories and maintained service identities.
- Bounded name/code/description search plus category, service, and version filters.
- Draft, active, superseded, inactive, and archived version history with explicit
  activation and immutable commercial snapshots.
- Labor, material, and other-direct planned components with truthful cost-readiness
  state; unit costs remain MANAGE-only.
- Owner-configured option groups support Good/Better/Best or other honest labels.
  Required/minimum and mutually exclusive/maximum selection constraints are sealed
  into snapshots and enforced when an Estimate is priced.
- Package services can carry customer scope plus labor/material/direct-cost component
  composition. Components are expectations, never Inventory consumption evidence.
- Bulk percentage/fixed proposals are previewed, reviewed, approved, and materialized
  as replay-safe successor drafts. Materialization never activates a price.
- Estimate creation now accepts multiple active services, governed alternatives,
  quantities, Customer/Location, customer message, terms, expiry, and authorized
  discounts. It creates immutable Price Book snapshots without asking operators for
  snapshot UUIDs.
- Customer decisions preserve identity, timestamp, optional contact/comment, and an
  optional sanctioned evidence reference. ACP does not claim legal-signature validity
  without an approved policy.
- Approved Estimates now have an authorized, idempotent API/UI conversion to Job.
  The conversion preserves the exact accepted revision and snapshot-lineage digest.
- Invoice creation remains bound to the completed Job, accepted Estimate revision,
  and the same immutable Price Book snapshot identities and amounts.

Templates and favorites are not introduced as parallel authority. A package service
or option group can be reused through the native Price Book; a broader template/favorite
domain should only follow a demonstrated operating need and owner policy.

## Qualification

- Fresh PostgreSQL zero-to-head and `current=head`: `n0p8q16g3t9u`.
- Affected Price Book, Estimate, Invoice, and idempotency suites: 78 passed.
- Frontend Price Book/Estimate/decision suites: 14 passed.
- Ruff, affected MyPy, Python compilation, ESLint, TypeScript, production build, and
  diff validation passed.

Enterprise should rerun those suites after protected composition, then deploy backend
and frontend together to Preview.

## Preview acceptance

1. As a MANAGE+ACTIVATE operator, create an ordered category and service with a clear
   customer description and separate internal notes.
2. Create Good, Better, and Best service alternatives with genuine scope distinctions;
   group them under a required, maximum-one option set.
3. Add expected labor, required/optional material descriptions and quantities, and any
   supported other direct cost. Confirm missing unit cost says insufficient evidence.
4. Create a draft price version, compare it with active authority, and activate it
   intentionally. Confirm the predecessor becomes historical.
5. Open Estimates; select Customer, Location, Branch, the option set and one alternative.
   Add another service line and quantities, customer message, terms, and expiry.
6. Create the Estimate and confirm subtotal, discount, tax, total, descriptions, selected
   option, quantities, version identity, and customer-safe presentation.
7. Record presentation and sanctioned customer acceptance evidence. Confirm ACP makes
   no unsupported legal-signature claim.
8. Convert the approved Estimate to a Job. Retry once and confirm the same Job is returned.
9. Complete the Job through the sanctioned synthetic Preview workflow and create its
   Invoice. Confirm revision and snapshot identities match the sold Estimate.
10. Create and activate a later Price Book successor. Confirm the prior Estimate, Job,
    and Invoice totals and snapshot digests remain unchanged.
11. Preview a bounded percentage or fixed adjustment, cancel without effect, then repeat,
    approve, and materialize successor drafts. Confirm no draft activates automatically.
12. Repeat browsing/search and Estimate selection on a phone viewport. As a READ-only
    user, confirm internal costs and every mutation/activation control remain unavailable.

## Remaining owner gates

- Explicit authorization to activate selected real All County candidate cohorts.
- Accountant-approved tax treatment classes; no jurisdiction policy is inferred.
- Membership/discount authority and limits where member pricing is used.
- Approved customer acceptance/signature policy and sanctioned evidence mechanism.
- Resolution of retained source conflicts and material mappings where operationally
  required. Cost incompleteness alone does not silently become zero or block otherwise
  approved commercial use.

Real-world closure requires protected integration, Preview migration/deployment, and a
successful owner/technician execution of this script with authorized All County data.

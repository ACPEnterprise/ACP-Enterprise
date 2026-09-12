# Price Book operator readiness 1

Protected authority: `d4eee6f6b0bc178d58654f26f3ef2b9429332ab3`

## Foundation inventory

| Capability | State | Evidence / remaining work |
| --- | --- | --- |
| Company/Branch-scoped categories and parent grouping | BACKEND_READY | Native category model, restrictive historical references, create and optimistic edit/archive APIs |
| Category operator workflow | FRONTEND_READY | Create, rename, regroup, activate/archive, alphabetical browse and filtering |
| Service item identity and metadata | BACKEND_READY | Code, category, branch, customer/internal descriptions, lifecycle and optimistic version |
| Service item operator workflow | FRONTEND_READY | Search/filter, detail, create and optimistic metadata edit without displaying IDs |
| Draft/active/superseded price versions | BACKEND_READY | Draft editing, effective windows, transactional activation/supersession, inactivation/archive and overlap exclusion |
| Version operator workflow | FRONTEND_READY | Current version, future draft, effective dates, history, draft edit, review/activate and lifecycle actions |
| Labor/material inputs | BACKEND_READY | Typed quantity and optional unit cost; component ordering is immutable within each version |
| Internal-cost security | BACKEND_READY | Ordinary read catalog omits costs/internal notes; separate MANAGE-authorized operator catalog exposes them |
| Tax classifications | BACKEND_READY | Company-scoped taxable/non-taxable classifications and immutable snapshot evidence |
| Tax operator workflow | FRONTEND_READY | Create and select tax treatment during draft review |
| Option groups/options | BACKEND_READY | Selection bounds, ordered options, Company scope and snapshot enforcement |
| Option operator workflow | FRONTEND_READY | Create groups and attach customer-visible service options |
| Currency and effective dates | BACKEND_READY | ISO currency constraint, effective/expiration validation and active-window exclusion |
| Immutable commercial snapshots | BACKEND_READY | Idempotent, digest-bound Price Book snapshot with price, components, tax and option evidence |
| Audit/history | BACKEND_READY | Append-only audit entries for creation, draft edits, activation, supersession and lifecycle changes |
| Authorization | BACKEND_READY | Separate READ, MANAGE and ACTIVATE permissions; operator-cost API requires MANAGE |
| Category custom drag ordering | MISSING | Domain has hierarchy and alphabetical order but no persisted display-order contract; no field was invented |
| Service-item unit/quantity label semantics | MISSING | Quantity exists on components/snapshots, but no authoritative sell-unit field exists |
| Other direct-cost component | MISSING | Domain supports labor/material only; no unsupported component type was introduced |
| Tax lifecycle operator maintenance | PARTIAL | Tax creation/selection exists; inactivate/archive API is not defined |
| Option edit/archive operator maintenance | PARTIAL | Creation and snapshot enforcement exist; update/archive API is not defined |
| Real All County operating content | BLOCKED | Requires `PRICEBOOK.ALLCOUNTY.BUILD.1` and owner-approved content; no bulk content was created |

No schema change is required by this candidate.

## Delivered operator flow

The office route now supports:

`Price Book → search/filter → category → service item → detail → draft → labor/material cost → customer price → tax → options → effective date → review → activate`

Operators see names, codes, descriptions, state and effective dates rather than
database IDs or raw version keys. Active versions remain immutable; revisions
are made on drafts and activation transactionally supersedes an overlapping
active version. Archive/inactivate actions preserve referenced history.

Ordinary READ users continue to receive the existing public catalog, which does
not serialize internal descriptions or unit costs. The new `/operator` catalog
requires `COMPANY_PRICE_BOOK_MANAGE`. Activation remains separately protected by
`COMPANY_PRICE_BOOK_ACTIVATE`.

## Estimate integration readiness

The backend boundary is substantially present: Price Book creates immutable,
digest-bound commercial snapshots, and Estimate revisions require Company- and
Branch-scoped snapshot IDs, preserve snapshot digests, quantities, option-group
constraints and tax evidence. Approved Estimate truth therefore does not change
when a later Price Book version is activated.

The next `ESTIMATE.PRICEBOOK.INTEGRATION.1` milestone should add only the missing
operator contracts:

1. A read-only effective-item picker for the selected Estimate Branch and
   effective time; it must return operator labels, not require typed IDs.
2. Quantity and option selection that calls the existing idempotent snapshot
   endpoint before adding an Estimate line.
3. A customer-safe preview of unit price, extended amount, option selection and
   tax classification from the snapshot.
4. Estimate forms that submit the snapshot identity/digest internally and never
   expose raw identifiers to operators.
5. Explicit expired/no-effective-version and option-bound validation states.
6. Regression proving later Price Book supersession does not change an existing
   draft, accepted or approved Estimate revision.

This candidate does not alter Estimate behavior or add automatic pricing.

## Enterprise qualification

Run the Price Book backend suite against PostgreSQL, including optimistic
category/item edits and internal-cost serialization boundaries. Then run Ruff,
MyPy, frontend unit tests, TypeScript, ESLint, and the production frontend build.
Because there is no schema change, Alembic zero-to-head qualification is not
newly required by this candidate; normal protected integration still verifies
one head/current=head/zero drift.

Local supported-runtime results:

- CPython 3.12: Ruff passed, MyPy passed, compilation passed.
- Authorization/OpenAPI boundary: 3 passed.
- Price Book operator UI: 7 passed.
- TypeScript and focused ESLint passed.
- Production Vite build passed.
- Alembic reports one head: `d4f6h8j0l2n4`.
- Full Price Book suite: 3 passed and 15 PostgreSQL cases could not initialize
  because the local shell cannot resolve the configured `postgres` host. No
  application assertion failed; the 15 database-backed cases, including the new
  cost-security and optimistic-update regression, remain mandatory in protected
  PostgreSQL CI.

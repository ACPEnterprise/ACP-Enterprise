# All County Price Book build — owner review packet

## Current native structure

ACP already owns Company/Branch-scoped categories, service items, draft/active/
superseded/inactive/archived price versions, labor and material components,
tax classifications, customer option groups, immutable commercial snapshots,
audit entries, optimistic versions, and separately governed activation.

`READY_FOR_REVIEW` is a derived build-workspace disposition, not a new persisted
lifecycle status. Persisted lifecycle truth remains the existing domain status.
Bulk-created service items and versions are always `draft`. The bulk endpoint has
no activation behavior and requires `COMPANY_PRICE_BOOK_MANAGE`; activation still
requires the separate `COMPANY_PRICE_BOOK_ACTIVATE` command.

## Existing draft and reference content

No repository-owned or sanctioned local HCP Price Book record set was found.
Reference classification counts for this checkpoint are therefore:

| Classification | Count |
| --- | ---: |
| REFERENCE_ONLY | 0 |
| DRAFT_CANDIDATE | 0 |
| INCOMPLETE | 0 |
| CONFLICTING | 0 |
| UNSUITABLE | 0 |

This is not a claim that HCP has no Price Book. It means no evidence packet is
available in this lane, so no HCP content was inferred, copied, or promoted.
Current native runtime counts require an authorized read of the deployed
operator catalog after protected integration; this lane did not access Preview.

## Build workflow

Managers may paste tab-separated service rows or edit up to 100 rows in a
responsive workspace, assign existing categories and tax classifications, add
customer/internal descriptions, proposed sell prices, effective dates, and
labor/material quantities and costs. Validation occurs before save and reports
duplicate code/name, missing required identity/scope/tax/pricing fields, and
incomplete economics evidence. A valid batch is persisted atomically as new
service identities plus revision-one draft versions with audit entries.

Incomplete labor, material, or internal-cost evidence does not get hidden. It
keeps a row at `INCOMPLETE`, while otherwise valid work may still be saved as a
draft for later completion. Invalid identity, taxonomy, Branch, tax, price, or
effective-date evidence prevents the entire batch from being saved.

Existing single-record workflows remain available for category maintenance,
draft revision, option groups/options, review, activation, supersession,
inactivation, and archive.

## Owner-supplied fields

- Final category taxonomy and grouping.
- Service codes and names.
- Approved customer-facing and internal descriptions.
- Proposed sell prices and intended effective dates.
- Tax classification decisions.
- Labor/material quantities and authoritative internal costs where available.
- Customer option structure and compatibility.
- Final review and explicit authorization for any activation.

ACP can derive duplicate checks, Company/Branch scope, effective-version
eligibility, draft completeness, immutable snapshot digests, audit evidence,
version sequencing, and active-only Estimate picker eligibility from existing
authoritative contracts. ACP does not derive owner prices or taxonomy.

## Recommended build sequence

1. Owner approves category taxonomy and tax classifications.
2. Manager enters or pastes bounded batches and resolves hard validation errors.
3. Save draft batches; complete missing economics and option evidence through
   normal Price Book maintenance.
4. Review the incomplete and ready-for-review queues; reconcile duplicate names
   or codes without inventing identity.
5. Owner reviews proposed prices/effective dates and explicitly authorizes a
   bounded activation set.
6. An activation-authorized user activates approved versions individually under
   the existing optimistic-concurrency boundary.
7. Verify only active/effective versions appear in Estimate selection and that
   existing Estimate snapshots remain unchanged.

No real All County content or price was created or activated by this milestone.

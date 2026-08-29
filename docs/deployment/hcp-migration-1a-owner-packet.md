# HCP.MIGRATION.1A owner packet and blocker reduction

MIGRATION.1A reads the sealed SOURCE.4 and MIGRATION.1 packages and adds
reconciliation overlays; it does not change either package. Protected evidence
is stored at
`~/.acp-enterprise/migration/housecall-pro/hcp-migration-1a-20260828T120000Z`.
The owner packet digest is
`99c3b246062c04637856b767d7659c175c259a28939e6dbc20de2f3cb2d02ff3`.

## Machine-bindable owner decisions

An owner response binds a decision by its group identifier, binding digest,
and alternative identifier. Per-record overrides also require the provider
native ID and a reason. No default is applied merely because it is recommended.

| Decision identifier | Count | Evidence-supported recommendation |
| --- | ---: | --- |
| `HCP1A.CANCELED_BALANCE_JOBS.V1` | 296 | `HOLD_OPERATIONAL_RECONCILE_BALANCE`: preserve the canceled Job and financial assertions, but hold them from Day-1 operations until HCP/QBO reconciliation. |
| `HCP1A.RECENT_ZERO_BALANCE_CANCELED_JOBS.V1` | 3 | `MIGRATE_CANCELED_HISTORY_ONLY`: preserve recent canceled history without creating work or AR. |
| `HCP1A.EMPLOYEE_CROSSWALK.V1` | 7 | No automatic default. Owner-confirm existing Employee, authorize an Employee candidate, or hold assignments. |
| `HCP1A.BRANCH_SCOPE.V1` | 2 patterns | No automatic default. Bind the one HCP Business Unit assertion and select the default Branch for 277 open-work Jobs. |
| `HCP1A.UNLINKED_DAY1_ESTIMATES.V1` | 350 | `HOLD_UNTIL_AUTHORITATIVE_JOB_LINK`: the existing target requires a Job; no relationship may be invented. |

Every option is reversible before cutover because MIGRATION.2 persistence has
not run and final cutover is not authorized. Protected representative examples
contain source status, dates, balances, relationship IDs, and native identities
without adding source meaning.

## Mechanical reductions

Nineteen open-work Jobs lacked an embedded Location relationship. Exact native
Customer evidence resolves nine: each Customer has exactly one authoritative
native Service Location. Eight Customers have multiple native Locations and
require owner selection. Two Customers have no acquired Location and remain
explicit migration exceptions. No fuzzy or name-only matching was used.

The 1,195-Invoice packet reduces to:

- 897 canceled/voided, zero-due assertions without payment/refund evidence:
  mechanically classified as explicit exceptions;
- 298 nonzero or contradictory current-balance assertions: hold for later
  authoritative HCP/QBO comparison;
- within the 298: 57 open, 209 canceled, 21 voided, and 11 paid source statuses;
  30 contain 34 payment assertions and nine contain nine refund assertions;
  only three refund assertions expose native refund IDs.

Payment applications and unapplied amounts remain `ABSENT`. Status never
substitutes for payment allocation.

## Attachments

The qualified HCP API contract contains no established attachment endpoint.
Both the earlier probe and the bounded open-work request to
`GET /jobs/{id}/attachments` returned HTTP 404 with HTML, while acquired Job
list/detail/expanded schemas expose no attachment field. This does **not** prove
that the HCP UI has no attachments. Classification is
`ACQUISITION_INCOMPLETE_NOT_AUTHORITATIVE_ABSENCE`.

Residual request: for the 278 selected open-work Jobs only, obtain an HCP-native
UI/Support attachment metadata listing with parent Job native ID, artifact
identity/reference, filename/type/size/timestamp/author where available. Retrieve
content only for owner-designated continuity-critical artifacts and seal its
digest. This can be held from MIGRATION.2 and remains a cutover dependency.

## Isolated PostgreSQL target

An isolated PostgreSQL 16 cluster now listens only on `127.0.0.1:55432` with
import database `acp_hcp_rehearsal_import` and user `acp_hcp_rehearsal`. It has a protected, dedicated credential,
an owner-only data directory and no Preview or Production access. It was proven
empty, then advanced to Alembic head `e0a6c2d8f351`; Companies, Customers,
Customer migration runs, and Operational migration runs all remain zero. No HCP
migration candidate has been persisted.

The repository also contains `docker-compose.migration-rehearsal.yml` as the
portable equivalent. Both target contracts fail closed unless the environment,
host, database identity, empty-target requirement, and Preview/Production access
flags match exactly. Synthetic database-backed validation uses the separate
`acp_hcp_rehearsal` database; it cannot contaminate the import target.

## Recomputed readiness

Candidate totals remain 38,474: 16,622 automatic, 6,839 explicit exception,
998 owner-disposition-dependent, and 14,015 legacy/non-blocking. Mechanical
blockers remaining: zero.

After the five owner decisions are bound, MIGRATION.2 is mechanically startable
with the 298 balance assertions and unavailable open-work attachments held from
import as explicit external-evidence exceptions. Its preflight must re-prove
zero migration business rows and
must not connect to Preview or Production.

# HCP.MIGRATION.1 transformation rehearsal

HCP.MIGRATION.1 consumed the sealed HCP.SOURCE.4 package without changing it.
The package manifest, collection manifest, page checksums, native-ID
cardinality, appointment evidence, control lineage, and protected modes all
verified before transformation. Candidate and owner-review artifacts are
protected outside Git at
`~/.acp-enterprise/migration/housecall-pro/hcp-migration-1-20260828T000000Z`.

## Candidate result

The source-faithful candidate contract produced 38,474 unique candidates. Its
digest is stable under reversed input order. Dispositions are 16,613 automatic,
6,837 explicit exception, 14,015 legacy/non-blocking, and 1,009 owner
disposition. Candidate counts are:

| Domain | Candidates |
| --- | ---: |
| Customers | 5,296 |
| Embedded Contacts | 4,494 |
| Service Locations | 5,633 |
| Employees | 7 |
| Jobs | 5,801 |
| Appointments | 3,219 |
| Estimates | 1,307 |
| Invoices | 5,756 |
| Payments | 4,308 |
| Refunds with native IDs | 12 |
| Notes | 2,640 |
| Business Unit evidence | 1 |

The registered Customer export adapter independently replayed the sealed
Customer control: 5,248 source rows, 4,426 accepted, 822
`contact_name_unresolved` rejections, no duplicates, and 243 incomplete-address
child exceptions. Both runs produced transformation digest
`4e6c0a1ee023bec1962f03b4c1f3b817d2b082e655c6e9a02deac0d14e9e857b`.
The API-native candidates preserve the 43 referenced/list-omitted Customer
identities separately; the control adapter does not replace their source
evidence.

## Compact owner decisions

Five bulk decision groups replace record-by-record review where evidence is
identical:

1. **296 canceled/control-omitted Jobs with reported balances:** choose
   source-faithful migration with a balance exception, operational exclusion
   with preserved evidence, or accounting escalation.
2. **Three canceled/control-omitted Jobs changed during the control/acquisition
   window with zero reported balance:** migrate as canceled history or exclude
   operationally while preserving the source record.
3. **Seven HCP Employees:** map to an existing Enterprise Employee, create an
   Employee candidate, or exclude only with explicit evidence. Six have 1,825
   aggregate relevant Job assignments; no automatic name-only match was made.
4. **Branch scope:** decide one mapping for the single HCP Business Unit
   assertion (present on seven Jobs) and the owner-approved default Branch for
   277 of 278 open-work Jobs that lack Business Unit evidence.
5. **350 Day-1 Estimates without an authoritative Job relationship:** link to
   an owner-confirmed Job, migrate as an unlinked exception if the target
   contract permits it, or exclude operationally while preserving source
   evidence. Twelve source-status patterns permit bulk review; 281 contain only
   an `approved` option assertion.

The 299-Job packet consists of 245 `pro canceled` and 54 `user canceled`
source assertions. These statuses and balances are not corrected.

## Financial and open-work findings

The financial exception packet contains 1,195 Invoice assertions: 367 require
owner disposition and 828 are explicit exceptions. Source statuses are 975
canceled, 152 voided, 57 open, and 11 paid. Thirty contain payment assertions
and three contain refund assertions. All preserve their HCP status and due
amount; missing payment applications and unapplied amounts remain absent.
Direct HCP/QBO comparison remains pending because QBO evidence is not part of
the authorized SOURCE.4 package; the handoff requires both assertions and a
conflict classification when it is performed.

Open work is 278 Jobs: 251 scheduled, 18 needing scheduling, and nine in
progress. It includes 169 Notes. Nineteen lack a Service Location relationship.
A bounded GET against the selected Job attachment path returned provider HTTP
404, so attachment metadata/content remains absent rather than fabricated.
The owner must identify any required open-work attachment through the bounded
support/UI path before cutover.

Company isolation corroborated one HCP Company across 12,368 provider records
carrying Company evidence. Cross-company candidate count is zero. Branch
persistence remains fail-closed until the owner supplies the two Branch
decisions above.

## Gate

No database rehearsal was persisted because owner dispositions affect parent
Jobs, Estimates, Employees, Branch isolation, and current balances. This is the
smallest safe stop before **HCP.MIGRATION.2 — Non-Production Enterprise Import
Rehearsal**. MIGRATION.2 becomes startable after the five grouped decisions are
supplied. Production import and cutover remain unauthorized.

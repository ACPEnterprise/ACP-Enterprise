<!-- markdownlint-disable MD013 -->

# ACC.AP.READY.1 — Day-1 AP Runtime Readiness and Activation Closure

## Scope and authority

This readiness record was prepared from authoritative
`origin/customer-management-v1` at
`5f6649527d793a3f40d1a60d41af5e5c5c943ea7`. It specializes the accepted
[Accounts Payable contract](accounts-payable-vendor-contract.md), its
[runtime packet](acc-ap-1.packet.json), the
[QuickBooks exit data contract](quickbooks-exit-data-contract.md), and the
[Accounting integration control](integration-control.md).

This milestone closes or classifies pre-runtime inputs only. It does not start
`ACC.AP.1`, create or re-parent a migration, obtain or import QuickBooks data,
change Preview or Production, rehearse, activate, or cut over.

## Readiness conclusion

`ACC.AP.1` is **NOT DEPENDENCY-READY — WAITING_ON_SLOT_3**. Its contract,
runtime boundary, generic vendor/bill/credit/subledger/disbursement semantics,
permissions, Business Events, and validation expectations are authoritative.
The remaining policy and source facts below are fail-closed activation inputs;
they must not be guessed or copied from synthetic fixtures.

The runtime becomes startable only after all of the following are true in a
freshly fetched authoritative view:

1. `PAY.1-3.ACCEL` slot 3 is integrated on
   `origin/customer-management-v1`, or an authoritative explicit
   migration-free disposition is integrated for it.
2. The fetched branch has exactly one Alembic head and the completed slot-3
   disposition is unambiguous.
3. A separate Owner Start is issued for the exact `ACC.AP.1` packet from that
   fetched SHA in an isolated, zero-behind worktree.

Owner, Finance, and source-evidence activation gates may remain fail-closed
during implementation, but no affected workflow may activate until its inputs
are accepted.

## Prerequisite classification

| Prerequisite | Classification | Closure or exact remaining input |
| --- | --- | --- |
| Vendor identity requirements | `RESOLVED_BY_AUTHORITY` | AP owns Company-scoped immutable vendor UUID/code, legal/display name, lifecycle, terms snapshot defaults, version, provenance, and archive history. Codes and identities are never reused; restricted banking/tax data is excluded from general events. Actual source identities and vendor facts remain source evidence below. |
| QuickBooks/source vendor mapping requirements | `RESOLVED_BY_AUTHORITY` | Map by immutable source Company and vendor identity plus checksum/digest, never display name. Ambiguous, contradictory, duplicate, or cross-Company mappings fail closed. The actual export and stable IDs are `SOURCE_EVIDENCE_REQUIRED`. |
| AP control account mapping requirements | `FINANCE_INPUT_REQUIRED` | Finance must identify the active same-Company AP control account from accepted COA/control evidence and approve its effective/versioned Core control assignment. AP cannot choose or post arbitrary manual lines to it. |
| Expense/asset/tax/inventory mapping inputs | `FINANCE_INPUT_REQUIRED` | Finance must approve complete effective mappings for applicable expense, prepaid, fixed-asset, inventory-asset, tax, freight, discount, and other classifications. Capitalization, recoverable tax, sales/use tax, 1099, landed-cost, and inventory policies are never inferred. |
| Disbursement evidence requirements | `SOURCE_EVIDENCE_REQUIRED` | A record requires verified authorization or settlement evidence from the approved money-movement owner: Company, vendor/payee, amount/currency, effective date, method category, non-sensitive external reference, source identity/digest, actor/approval, allocation, and Accounting receipt. AP stores no credentials and initiates no money movement. |
| Approval/SOD roles | `OWNER_INPUT_REQUIRED` | Owner must bind named authorized humans to the eight accepted AP permissions and establish distinct preparer/approver, duplicate requester/reviewer, disbursement recorder/approver, and reconciler/variance-disposition identities. Finance posting/period/final-approval roles remain Accounting-owned. |
| Duplicate-bill override authority | `FINANCE_INPUT_REQUIRED` | Finance must approve normalization, hard/possible duplicate, evidence, reason, and escalation policy plus any approval limits. A possible duplicate needs an independently authorized reviewer; a hard duplicate remains blocked. Owner must then bind eligible humans under the accepted SOD rule. |
| Fiscal-period dependencies | `SOURCE_EVIDENCE_REQUIRED` | Company settings and Finance-confirmed fiscal calendar must evidence fiscal-year start, period bounds, current close date/status, timezone, basis, and currency. Core period authority is resolved: closed periods reject new/corrected facts and AP cannot reopen them. |
| AP aging policy inputs | `FINANCE_INPUT_REQUIRED` | Finance must approve AP bucket boundaries and presentation using evidenced QuickBooks settings where available. AP supplies immutable aging inputs and Company business-timezone semantics; Financial Reporting owns presentation. |
| Required Business Events | `RESOLVED_BY_AUTHORITY` | Required event names and payload invariants are frozen in the AP contract and packet: vendor created/mapped; bill approved/reversed; vendor credit issued/applied; disbursement recorded/reversed; reconciliation required. |
| Frontend/operator acceptance criteria | `RESOLVED_BY_AUTHORITY` | The packet requires responsive accessible vendor, bill, duplicate review, credit, disbursement-evidence, open-item, aging-input, reconciliation, and posting-status workflows; route/API authorization; permission-negative and Company/Branch isolation tests; explicit loading/empty/error/conflict/reconciliation states; and no payment-initiation or unrestricted-sensitive-data surface. Named operator role bindings remain `OWNER_INPUT_REQUIRED`. |
| Preview activation gates | `OWNER_INPUT_REQUIRED` | Separate Owner Preview authorization after accepted `ACC.AP.1` implementation/integration and `ACC.IC.1`; required Finance/source inputs, sanitized validation, backup/restore, release, and rollback evidence must be accepted. This record grants none of them. |
| Production activation gates | `OWNER_INPUT_REQUIRED` | Separate Production authorization after healthy accepted Preview, aggregate financial/security regression, Finance control acceptance, operational rollback evidence, and zero unexplained control variance. This record grants none of them. |
| Import/cutover gates | `SOURCE_EVIDENCE_REQUIRED` | Real import/rehearsal requires the accepted immutable QuickBooks package, manifests/checksums, mappings, controls, restricted custody, security approval, backup/rollback, accepted target schemas, independent Finance approval, and separate Owner authority. Final cutover additionally requires freeze/change control and Owner go/no-go. |
| Migration parent readiness for slot 4 | `WAITING_ON_SLOT_3` | Current authoritative head is `w8m0i2k4n619`. It is observation only, not the slot-4 parent promise. Slot 4 may parent only the actual single head fetched after slot 3 integrates or receives an authoritative migration-free disposition. |

## Owner inputs required

- Issue a separate `ACC.AP.1` Start only after the exact dependency trigger above.
- Name the QuickBooks export operator and restricted evidence custodian; neither
  may independently approve their own package.
- Bind named human identities to the accepted AP permissions and SOD roles,
  including duplicate review, disbursement approval, and variance disposition.
- Approve the non-PO authority model and the operational owners allowed to
  provide disbursement authorization/settlement evidence.
- Later issue separate Preview, Production, import/rehearsal, and final cutover
  decisions; none is implied by runtime Start.

## Finance inputs required

- Accept functional currency and accounting basis from controlled source
  evidence; synthetic `USD` or `accrual` values are not Company facts.
- Approve the AP control account and complete effective expense, prepaid,
  asset, inventory, tax, freight, discount, cash, and clearing mappings that
  apply to Day 1.
- Approve terms, duplicate normalization/override policy, approval limits,
  matching/tolerance, non-PO, capitalization, recoverable-tax, sales/use-tax,
  landed-cost, and disbursement-method policies as applicable.
- Approve AP aging buckets/presentation and fiscal-period schedule/close facts.
- Identify the independent Finance reviewer and accept exact reconciliation
  workpapers; any unexplained variance blocks activation.

## Exact QuickBooks Online evidence required

No raw export belongs in Git. Evidence must identify one stable source Company,
export operator/time, report/export definition and version, basis, currency,
timezone/locale, cutoff, filters, format/encoding, byte size, and raw SHA-256.
Machine-readable rows and human-readable control reports have distinct roles;
PDF controls are not loader rows.

| Artifact | Minimum fields and control evidence | AP use |
| --- | --- | --- |
| Vendors | Stable source Company ID and vendor ID; display/legal name fields available in the source; active/inactive state; terms; currency if exposed; timestamps/version or equivalent; referenced open-item coverage; export settings and digest. Restricted bank/tax fields must be excluded unless separately required and authorized. | Deterministic source-to-AP identity mapping without name matching. |
| Open bills | Stable transaction and vendor IDs; document number; bill/received/due dates where exposed; terms; currency; line/order identity; description, quantity/unit where applicable; account/item/tax references; net/tax/total/open amounts; application links; PO/receipt references if present; void/deleted state; signs; cutoff and basis. | Bill/open-item provenance, mapping inputs, duplicate evidence, and opening reconciliation. |
| Vendor credits | Stable credit/vendor IDs; credit date, number/reference, currency; line/account/item/tax references; original and unapplied amounts; applications/unapplications and linked bill IDs; void/deleted state; signs; cutoff and basis. | Credit identity, open balance, applications, and reconciliation. |
| AP aging | Aging detail by vendor and open item at the common cutoff; stable vendor/transaction IDs; bill/due dates; original/open amounts; credits/applications/disbursements; bucket definitions and boundary semantics; timezone, basis, currency, filters; total tied to AP control and signed control report. | Opening-item completeness, aging-policy evidence, and control reconciliation. |
| AP control account | Active COA machine export plus control report with stable account ID, number/name, type/subtype/classification, active state, parent, currency where applicable, and explicit AP-control designation; same-cutoff TB and AP-aging tie-out. | Finance-approved Core control assignment and exact AP-to-GL reconciliation. |
| Expense/asset/tax mappings | Active COA stable IDs/classifications plus source account/item/tax-code IDs used on AP lines; source names only as labels; effective state, parent, type/subtype, jurisdiction/recoverability where evidenced, inventory/fixed-asset/prepaid indicators, and representative sanitized layouts. Finance-approved one-to-one/coded crosswalk with effective version and dispositions for every used source value. | Fail-closed line classification and posting-rule inputs; no inferred tax, capitalization, or inventory treatment. |

Before rehearsal/cutover, the package must additionally include the final native
QuickBooks archive, complete artifact inventory, common-cutoff exports and
controls, export logs, custody/retention and restore/fixity evidence, final
freeze/change control, row-level rejects/dispositions, signed workpapers, and
checksum-bound independent Finance acceptance.

## Runtime acceptance and activation gates

Implementation acceptance remains the exact validation list in
`acc-ap-1.packet.json`. Operator acceptance must demonstrate, with synthetic or
otherwise authorized non-Production evidence, that:

- permitted roles can complete their bounded vendor, bill, credit,
  disbursement-recording, reconciliation, and reporting tasks;
- forbidden roles, self-approval, cross-Company/Branch access, stale writes,
  duplicate conflicts, over-application, closed periods, missing mappings, and
  missing/contradictory evidence fail closed;
- frontend states make pending posting, unknown disbursement outcome, duplicate
  review, reconciliation required, and unavailable aging/control evidence
  explicit rather than displaying success or zero; and
- no UI or API initiates payment, stores credentials, imports QuickBooks data,
  or treats a PO/receipt as a liability.

Preview cannot begin until runtime implementation is accepted and integrated in
slot order, `ACC.IC.1` is accepted, activation inputs are evidenced, and Owner
separately authorizes Preview. Production cannot begin until Preview evidence,
Finance controls, rollback readiness, security/aggregate regression, and Owner
Production approval are accepted. Import, rehearsal, and cutover remain their
own later gates.

## Slot-4 parent rule

At this record's authoritative SHA, the single Alembic head is
`w8m0i2k4n619`; slot 3 has not supplied an integrated successor or authoritative
migration-free disposition. Therefore no slot-4 revision may be created now.

Immediately before `ACC.AP.1` starts, fetch
`origin/customer-management-v1`, require the worktree to be zero-behind, prove
that slot 3 is integrated or authoritatively migration-free, and run `alembic
heads`. Exactly one returned revision becomes the proposed slot-4 parent. Fetch
and repeat those checks before integration. Any changed head must be handled
under the integration control with recorded review and full validation; an
already published revision, sibling head, ambiguous ancestry, overlapping DDL,
semantic incompatibility, or changed financial meaning stops the work. No
sibling head, merge revision, or silent semantic re-parenting is allowed.

<!-- markdownlint-disable MD013 -->

# ACC.DATA.1 — QuickBooks Exit Data Contract

## 1. Authority and boundary

This contract freezes the data package needed to retire QuickBooks as the
runtime accounting authority under [ACC.CUTOVER.0](day-1-control-contract.md).
Day 1 consists of validated opening balances, required open items, and an
immutable QuickBooks archive. It does not recreate full history inside ACP.

This milestone defines data and evidence only. It does not access QuickBooks,
extract or import data, create schemas or Alembic revisions, run `ACC.MIG.1`,
change customer data, deploy, enter Preview or Production, or perform cutover.
No real exports, credentials, private keys, customer names, account numbers, or
other private data may be committed to Git.

No QuickBooks export samples or authoritative column headers were present in
the repository at contract freeze. Consequently, every source layout is
`SOURCE EVIDENCE REQUIRED`. Names in this document are ACP semantic facts and
canonical artifact kinds—not claims about QuickBooks field names. A source
adapter may not be designed until a sanitized header/sample or vendor report
definition proves the corresponding source layout.

## 2. Package-wide rules

### 2.1 Authority, identity, and time

- QuickBooks is authoritative only through the owner-approved cutover instant.
- `source_company.stable_id` must be a stable identifier evidenced by the export or
  owner-approved company record; display name alone is insufficient.
- Every source account, customer, vendor, transaction, and open-item identity
  must retain its stable source identity. If an export lacks one, Finance must
  approve a deterministic composite identity before development continues.
- The manifest binds exactly one source company to one ACP Company and an
  explicit Branch allocation policy. Unresolved Company/Branch allocation is a
  blocking Finance disposition, never a default.
- Dates use ISO `YYYY-MM-DD`; timestamps use RFC 3339 with an explicit offset.
  Source timezone, currency, locale, decimal convention, accounting basis,
  report filters, and inclusive cutover instant must be recorded.
- Day 1 assumes the architecture-approved company currency. Any foreign-
  currency account or open item requires evidenced source currency, native
  amount, book-currency amount, and rate policy; otherwise stop for Finance.

### 2.2 Files, checksums, and immutability

- The only loader-eligible row formats are CSV or XLSX whose actual layout has
  been accepted from source evidence. JSON may be used for ACP manifests and
  normalized staging records, not presumed as a QuickBooks export format.
- PDF is control evidence only. It cannot supply loader rows. A native backup
  or vendor-native export is archive evidence only unless separately proven.
- Every file is hashed as its exact raw bytes using SHA-256 and recorded with
  byte size, media type, original filename, export timestamp, artifact kind,
  and producing report/export definition. Copying or renaming must not alter the
  recorded content digest.
- The manifest is UTF-8 JSON. Its deterministic digest is SHA-256 over RFC 8785
  JSON Canonicalization Scheme bytes with `manifest_sha256` omitted. The final
  manifest records that digest. A changed byte, metadata value, disposition, or
  transformation version produces a different package identity.
- Source files, the accepted manifest, transformed records, rejects,
  dispositions, controls, approvals, and execution logs are append-only. A
  correction creates a new package/version and preserves the prior evidence.

### 2.3 Acceptance and rejection

Every expected artifact has exactly one terminal package state:

1. `accepted` with its checksum, schema evidence, row accounting, and controls;
2. `rejected` with immutable reason codes and no loader eligibility; or
3. for a conditional artifact only, `not_applicable`, supported by preparer and
   independent Finance approval plus a zero/nonexistence control.

`finance_disposition_required` is nonterminal and blocks the package. Every
source row must be counted exactly once as accepted, rejected, or awaiting a
recorded Finance disposition. Rejected or ambiguous rows are never silently
dropped, coerced to zero, assigned a fabricated identity, or posted to a
suspense account without an expressly approved disposition. Required artifacts
cannot be waived by `not_applicable`.

Normalization is non-destructive: trim only documented presentation whitespace,
preserve original text and identifiers, parse dates/decimals under the recorded
locale, use exact decimal arithmetic, prohibit binary floating point for money,
and retain raw row number plus source digest. Blank and zero remain distinct.
Duplicate stable identities, invalid dates, unparseable amounts, missing keys,
unbalanced controls, and unknown enumerations reject the affected row and block
cutover until dispositioned.

## 3. Source artifact catalog

All catalog entries inherit the package-wide identity, normalization, checksum,
validation, rejection, and disposition rules. “Facts” below are semantic facts;
the mapping from actual QuickBooks headers remains `SOURCE EVIDENCE REQUIRED`.
The source authority is the final QuickBooks company export/report at the
approved cutoff, except the native archive, whose authority is the native
QuickBooks backup/export itself.

| Canonical artifact kind | Status | Accepted evidence/format | Required semantic facts | Validation and reconciliation target |
| --- | --- | --- | --- | --- |
| `chart_of_accounts` | Required | Machine-readable active-account export plus human-readable control report | Stable source account ID, account number/name, active state, source type/classification, parent if any, currency if applicable | Unique stable identities; types mapped without COA redesign; all posting/control accounts resolve; agrees to trial-balance accounts |
| `trial_balance` | Required | Machine-readable cutover trial balance plus signed/PDF control report | Source account identity, debit or credit closing balance, report cutoff, basis, currency | Debits equal credits; nets to zero; every nonzero account maps once; equals total ACP opening GL |
| `gl_detail` | Required | Machine-readable GL detail for the Finance-approved support period plus report control | Journal/transaction identity where exposed, source account, posting date, amount/debit-credit meaning, reference, modification metadata if exposed | Scope and totals agree to the trial balance or Finance-approved roll-forward; supports audit and unexplained-balance investigation; not loaded as full history |
| `open_customer_invoices` | Required | Machine-readable open-invoice export plus control report | Stable invoice and customer IDs, document/date/due date, original and open amounts, tax/credit application facts, currency if applicable | Unique open-item identity; open amount is valid; sum plus related credits/receipts agrees to AR aging and AR control |
| `customer_credits` | Required | Machine-readable open-credit export plus control report | Stable credit and customer IDs, date, original/unapplied amounts, application links, currency if applicable | No double application; unapplied amount agrees to customer/open-item controls and AR control |
| `ar_aging` | Required | Machine-readable aging plus signed/PDF report | Stable customer identity, open-item identity where available, aging date/bucket, open amount | Customer/item totals agree to open AR package and GL AR control at the same cutoff |
| `unapplied_customer_receipts` | Required | Machine-readable unapplied-receipt export plus control report | Stable receipt/customer IDs, receipt date, amount, payment reference, deposit/undeposited status | Each receipt appears once; total agrees to AR/undeposited-funds controls as applicable |
| `undeposited_funds` | Required | Machine-readable undeposited transaction listing plus control report | Stable receipt/payment identity, date, amount, source customer if applicable, deposit status | Detail sum equals undeposited-funds GL control; no item also appears as deposited |
| `open_vendor_bills` | Required | Machine-readable open-bill export plus control report | Stable bill and vendor IDs, document/date/due date, original/open amount, currency if applicable | Unique open-item identity; sum with credits agrees to AP aging and AP control |
| `vendor_credits` | Required | Machine-readable open-vendor-credit export plus control report | Stable credit/vendor IDs, date, original/unapplied amounts, application links | No double application; totals agree to vendor/open-item and AP controls |
| `ap_aging` | Required | Machine-readable aging plus signed/PDF report | Stable vendor identity, open-item identity where available, aging date/bucket, open amount | Vendor/item totals agree to open AP package and GL AP control at the same cutoff |
| `bank_accounts` | Required | Machine-readable account/balance evidence plus reconciliation report | Stable source account ID, masked account identity, statement and book balances, last reconciliation date | Book balance equals mapped opening GL; statement difference is fully explained by reconciling items |
| `cash_accounts` | Required | Machine-readable cash-account balances plus control report | Stable source account ID, balance, cutoff | Sum equals mapped cash opening GL accounts |
| `credit_card_balances` | Required if any credit-card account exists; otherwise approved `not_applicable` | Machine-readable balance/detail plus statement control | Stable source account ID, book/statement balance, cutoff, outstanding activity | Equals mapped liability opening balance; differences fully dispositioned |
| `loan_balances_and_terms` | Required if any loan exists; otherwise approved `not_applicable` | Machine-readable balance evidence plus lender statement/control | Stable source account ID, lender/source identity, principal balance, accrued interest if booked, cutoff; terms only when evidenced | Equals mapped liability/receivable opening balance; statement variance dispositioned |
| `outstanding_checks` | Required if any bank reconciliation has outstanding checks; otherwise approved `not_applicable` | Machine-readable reconciliation detail | Stable check/transaction ID, account ID, date, amount, payee source ID if exposed | Unique and included exactly once in bank reconciliation; not duplicated in open AP |
| `deposits` | Required if deposits in transit or uncleared deposits exist; otherwise approved `not_applicable` | Machine-readable reconciliation detail | Stable deposit ID, account ID, date, amount, constituent receipt links when exposed | Unique; agrees to bank and undeposited-funds reconciliation |
| `transfers` | Required if uncleared/in-flight transfers exist; otherwise approved `not_applicable` | Machine-readable transfer/reconciliation detail | Stable transfer ID, source/destination account IDs, dates, equal source/destination book amounts | Both legs resolve once; inter-account total nets to zero |
| `reconciling_items` | Required for every nonzero statement-to-book difference; otherwise approved `not_applicable` | Machine-readable reconciliation detail plus signed reconciliation | Stable item/account ID, date, amount, type, clearing status, explanation | Explains statement-to-book difference exactly; each item dispositioned once |
| `sales_tax_liabilities` | Required | Machine-readable liability detail plus jurisdiction control report | Stable jurisdiction/agency identity, filing period, taxable basis if exposed, tax liability, payments/credits due | Jurisdiction totals equal mapped sales-tax control accounts; unresolved jurisdiction blocks cutover |
| `inventory_control_balance` | Required | Machine-readable inventory valuation/control evidence plus signed report | Stable inventory control account, valuation cutoff/method evidence, financial control total | Equals mapped inventory asset/control opening balance; operational item quantities are outside this contract unless separately approved |
| `payroll_liabilities_accruals` | Required | Machine-readable payroll liability/accrual balances plus control report | Stable liability account/agency identity, period, amount, due date if exposed | Equals mapped payroll liability/accrual opening accounts |
| `payroll_summary` | Required | Latest payroll-provider/QuickBooks summary and signed control | Covered pay period, gross/net/control totals, taxes, deductions, employer liabilities | Agrees to booked payroll balances and identifies any post-cutoff obligation; no employee credentials or unnecessary sensitive detail in Git |
| `fixed_assets` | Required if fixed assets exist; otherwise approved `not_applicable` | Machine-readable register plus GL control | Stable asset identity/category, placed-in-service date, cost, accumulated depreciation, net book value | Cost and accumulated depreciation totals equal mapped GL controls |
| `accumulated_depreciation` | Required if fixed assets exist; otherwise approved `not_applicable` | May be a separately controlled report or proven column set in fixed-asset register | Stable asset/category identity, accumulated depreciation, cutoff | Agrees to fixed-asset register and mapped contra-asset control |
| `equity` | Required | Machine-readable account balances plus control report | Stable source account identity, classification, closing balance | Equals mapped opening equity accounts and participates in balanced opening entry |
| `retained_earnings` | Required | Machine-readable balance/control report | Stable source account identity, closing balance, fiscal-year context | Equals mapped retained-earnings opening account; no automatic reclassification without Finance approval |
| `prepaids` | Required if any prepaid balance exists; otherwise approved `not_applicable` | Machine-readable schedule plus GL control | Stable schedule item/account identity, remaining balance, relevant dates | Schedule total equals mapped prepaid GL control |
| `accruals` | Required if any non-payroll accrual exists; otherwise approved `not_applicable` | Machine-readable schedule plus GL control | Stable accrual/account identity, amount, period, reversal treatment if evidenced | Schedule total equals mapped accrual GL control; reversal policy is Finance-approved |
| `customer_identities` | Required | Machine-readable active identities plus every identity referenced by open items | Stable source customer ID, display reference, active state; Company/Branch mapping evidence | Every AR row resolves to exactly one ACP party; no display-name-only matching |
| `vendor_identities` | Required | Machine-readable active identities plus every identity referenced by open items | Stable source vendor ID, display reference, active state; Company/Branch mapping evidence | Every AP row resolves to exactly one ACP party; no display-name-only matching |
| `accounting_periods` | Required | Machine-readable or controlled configuration evidence | Fiscal year/calendar, period bounds, open/closed state, cutoff period | ACP opening date and period controls match approved cutover; ambiguous/overlapping periods reject |
| `export_metadata` | Required | Manifest metadata and export logs/screenshots where needed | Source company identity, product/edition/version, export timestamp/operator, timezone, locale, basis, filters, cutoff, report definition/version | Every artifact is reproducible and bound to the same company/cutoff or has an approved reason |
| `native_archive` | Required | Native backup/export and immutable report/export collection in approved restricted storage | Archive inventory, source company, creation timestamp, product/version, byte size, digest, custodian, storage/retention reference | Restore/readability rehearsal succeeds on an isolated authorized system; archive digest matches manifest |

The `latest_payroll_summary` requirement is satisfied by `payroll_summary`.
The separate references to loan balances and loans are satisfied by
`loan_balances_and_terms`. Required GL detail means the final Finance-approved
support scope, not full historical migration.

## 4. Deterministic opening-state contract

`ACC.MIG.1` transforms accepted source rows into these canonical target record
classes. Target persistence names are deliberately not prescribed before the
Accounting runtime schemas are accepted.

| Target record class | Required content and behavior |
| --- | --- |
| Account mapping | Source company/account identity to one ACP Company, Branch policy, ACP account identity/type, effective package and provenance |
| Opening GL journal | One controlled opening journal set for the approved instant, line-level account/Company/Branch, exact debit or credit, source controls, package/transformation identity; total debits equal credits |
| Open AR item | Stable source invoice/credit/receipt identity, customer mapping, dates, original/open amount, applications, currency facts if applicable, provenance; aggregate equals AR control |
| Open AP item | Stable source bill/credit identity, vendor mapping, dates, original/open amount, applications, currency facts if applicable, provenance; aggregate equals AP control |
| Unapplied receipt/credit | Stable source identity, party mapping, remaining amount, application state and provenance; cannot be duplicated in AR/AP or cash controls |
| Bank/cash opening state | Account mapping, book balance, statement evidence, last reconciliation and linked outstanding/reconciling items |
| Undeposited-funds state | Stable receipt identity, amount and deposit state; aggregate equals the mapped control account |
| Tax-liability state | Jurisdiction/agency mapping, filing period, liability and credit/payment facts; aggregate equals tax controls |
| Inventory financial control | Company/Branch allocation and financial control balance at cutoff; no item-level operational import is implied |
| Payroll-liability state | Liability/agency mapping, covered period, amount and due-date facts if evidenced; no payroll runtime replacement is implied |
| Other opening schedule | Loans, fixed assets/depreciation, equity, retained earnings, prepaids and accruals, only where applicable and fully tied to mapped GL controls |
| Rejection/disposition record | Package/artifact/raw-row identity, immutable reason, observed value reference, state, preparer and independent approver evidence, resolution and replacement linkage |
| Control-total record | Named equation, source amount/count, transformed amount/count, target amount/count, variance, currency, cutoff, evidence digests and approval state |

Every target record retains the source package ID, artifact digest, raw row
locator, transformation version, stable source identity, target identity, and
creation evidence. Replaying the same accepted package and transformation
version must return the same result without duplicate records or postings.
Changing either creates a distinct rehearsal; it never mutates a prior result.

## 5. Reconciliation and cutover-blocking controls

All equations use exact decimals in the architecture-approved currency and the
same cutoff/basis:

- each QuickBooks closing account balance equals its ACP opening balance;
- opening journal debits equal opening journal credits;
- trial-balance debits equal credits and its net is zero;
- opening assets equal liabilities plus equity;
- AR control equals open invoices less credits/applications plus properly
  classified unapplied customer items;
- AP control equals open bills less vendor credits/applications;
- AR and AP aging totals equal their respective controls;
- undeposited-funds detail equals its GL control;
- bank/cash book balances equal mapped GL balances and each statement variance
  equals the signed reconciling-item total;
- tax liability detail by jurisdiction equals mapped tax control accounts;
- inventory financial control evidence equals the mapped inventory control;
- payroll, loan, fixed-asset/depreciation, prepaid, accrual, equity, and retained-
  earnings schedules equal their mapped GL controls where applicable;
- source rows = accepted rows + rejected rows + rows awaiting disposition, with
  each source row in exactly one category; and
- transformed accepted rows = loaded rows + explicitly nonposting accepted
  evidence rows, without duplication.

Every variance has amount, affected control, source evidence, owner/preparer
proposal, independent Finance disposition, and resolution linkage. Any
unexplained or unapproved nonzero variance, missing required artifact, terminal
row-accounting mismatch, checksum mismatch, unbalanced journal, unresolved
identity, or Company/Branch ambiguity blocks rehearsal acceptance and cutover.

## 6. Immutable QuickBooks archive

The archive is retained outside Git in encrypted, access-controlled, read-only
storage with at least two independently managed copies. It contains the native
backup/export sufficient for later authorized restoration, all final reports
and machine exports, report settings, manifest/checksums, reconciliation
workpapers, dispositions, approvals, product/version information, and an index
usable without ACP. Retention must satisfy the owner, CPA, tax, legal, and
records policy; this contract does not invent a retention duration.

Archive custodians and access events are auditable. Periodic fixity checks
recompute digests without rewriting evidence. A restore/readability rehearsal
uses an isolated authorized environment and records its result. QuickBooks may
be retired to read-only/archive use only after reconciliation, independent
Finance approval, owner activation, and the separately authorized cutover.
Archive availability never authorizes QuickBooks runtime dependence after
cutover and does not require historical transactions to be recreated in ACP.

## 7. Machine-enforceable `ACC.MIG.1` handoff

The normative manifest schema is
[`acc-mig-1-input-manifest.schema.json`](../../project/accounting-cutover/schemas/acc-mig-1-input-manifest.schema.json);
the repository fixture is explicitly synthetic and demonstrates structure, not
a cutover-complete package. Before a package is loader-eligible, validation must
require exactly one `primary_source` entry for every catalog kind:
unconditional kinds must be `accepted`, while conditional kinds must be
`accepted` or approved `not_applicable`. Additional `control_report` and
`archive_evidence` entries may share a kind, but every artifact ID and path must
be unique and only an accepted `primary_source` may supply loader rows. The
future loader must:

- accept only artifact kinds enumerated by the schema and only terminally
  `accepted` artifacts as row inputs;
- require one immutable manifest, valid file SHA-256/size checks, accepted
  source-layout evidence, contract and transformation versions, exact source
  company and target Company/Branch binding, cutoff, basis, timezone, locale,
  currency, row accounting, and named control totals;
- reject the complete run before persistence when a required artifact/control
  is missing, any digest or byte size differs, a path escapes the mounted
  read-only package, the company binding differs, or a nonterminal disposition
  exists;
- key idempotency by source company, package ID, manifest digest,
  transformation version, target Company, and rehearsal/execution mode;
- preserve immutable raw-row, normalized-row, rejection, disposition,
  transformation, control, and approval evidence;
- run rehearsals inside a transaction or disposable database and roll back or
  destroy the rehearsal target after exporting control evidence; never mutate
  Production, QuickBooks, or the source archive;
- generate deterministic counts, totals, mappings, rejects, dispositions,
  opening journal preview, and reconciliation report before any approval gate;
  and
- fail closed. Partial posting, silent skips, guessed mappings, suspense
  balancing, checksum bypass, and continuation after an invariant failure are
  prohibited.

`ACC.MIG.1` architecture/implementation may use only sanitized synthetic
fixtures until separately authorized source evidence is provided. Loader
implementation is a separate milestone. Any real-data rehearsal, import,
Production migration, or cutover is `TYPE C`, requires owner Start, independent
Finance acceptance of controls, the then-current approved target schemas, an
approved backup/rollback plan, security approval for restricted data handling,
and the Preview/Production gates. Final Production/cutover authority remains
Owner; the same identity cannot act as preparer and independent approver.

If `ACC.MIG.1` needs persistence, its migration serializes after
`ACC.CORE.1 → INVOICE.1-3.ACCEL → PAY.1-3.ACCEL → ACC.AP.1 → ACC.POST.1 → ACC.RPT.1`.
At integration it must descend from the then-current single authoritative
Alembic head. No sibling head, force-push, or unjustified merge migration is
allowed.

## 8. Source-evidence gap list

### Required immediately for development

Sanitized evidence may contain headers and structurally representative fake
rows only; no real customer, vendor, employee, account, tax, bank, or transaction
data is needed in Git.

- QuickBooks product/edition/version and source-company stable-identity evidence.
- For every catalog artifact, the exact export/report name, actual headers,
  format/encoding, report settings, filters, basis, locale, timezone, and a
  sanitized structurally representative sample or vendor definition.
- Evidence showing which stable IDs QuickBooks exposes for accounts, customers,
  vendors, transactions, invoices, bills, credits, receipts, and reconciliation
  items; any absent identity needs a Finance-approved deterministic rule.
- Current COA classification evidence, including control-account designation
  and the Company/Branch allocation source/rule.
- Evidence for debit/credit sign semantics, date semantics, open amount,
  application links, aging buckets, undeposited/deposit state, and void/deleted
  or inactive records in the selected exports.
- Currency, decimal, accounting-basis, fiscal-period, and cutoff conventions;
  explicit confirmation whether any multicurrency facts exist.
- Owner inventory of which conditional artifacts exist and which may seek a
  signed `not_applicable` disposition.
- Approved transformation-version convention, rejection reason catalog, and
  secure non-Git location/access model for restricted rehearsal data.

Until these arrive, source adapters and real-field mappings remain blocked as
`SOURCE EVIDENCE REQUIRED`; contract/schema and synthetic-loader architecture
can proceed.

### Required only for rehearsal/cutover

- Final native QuickBooks backup/export and complete archive inventory.
- Final raw machine exports and human-readable control reports for every
  required/applicable artifact, all produced from the same source company,
  basis, filters, and approved cutoff.
- File sizes, raw-byte SHA-256 digests, export logs/operator/timestamps, report
  settings, source timezone/locale/currency, and archive storage/custody evidence.
- Final transaction freeze evidence and post-export change control.
- Statements and signed reconciliations for bank, cash, credit cards, loans,
  deposits/transfers, and all reconciling items.
- Final AR/AP aging and open-item/application detail; tax jurisdiction controls;
  inventory, payroll, fixed-asset/depreciation, loan, prepaid, accrual, equity,
  and retained-earnings controls as applicable.
- Complete customer/vendor identities referenced by open items and approved
  target Company/Branch mappings.
- Row-level rejects/dispositions, all control workpapers, preparer signoff,
  independent CPA approval, archive restore/fixity evidence, ACP backup and
  rollback plan, security approval, and final Owner cutover authorization.

## 9. Readiness and remaining gates

This contract closes `ACC.DATA.1` only after its schema, synthetic fixture,
links, checksums, and invariants validate. It enables `ACC.MIG.1` architecture
and sanitized synthetic implementation to begin after separate Owner Start and
after accepted target Accounting schemas are available. Real-field adapters
remain blocked by the immediate source-evidence list. Real rehearsal, import,
Preview, Production, activation, and cutover remain separately gated.

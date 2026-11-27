# All County native Accounting admission preparation

Status: **prepared, blocked before native financial writes**

This packet advances the accepted archived QuickBooks reporting into a governed
native-admission design. It does not treat a report workbook as a transaction
loader, does not call QuickBooks, and does not create or post Accounting facts.

## Evidence binding

| Evidence | Qualified value |
|---|---|
| Source run | `qbo-production-20261119T235000Z` |
| Source records | 20,702 |
| Relationship identities | 97,093 |
| Source manifest | `b9a8bd5139bf70e80131c0c8096459e4f1c65576049ee58d91b683d8eeb5378f` |
| Bounded snapshot | `e4d672c1cdfca858e4a8e923a51a86627753c7ea1fedc695daa98066a5dc6041` |
| Manual custody manifest | `f6640c0d531eaa8a822e82f697b3aaead65c8ae7b52a3c527e9616642c4d4f4a` |
| Deterministic plan | `0e696c85ad25427ce1aa99ba0ab1c439824122e4a83e79d69319e7e13347248b` |
| Private plan-file SHA-256 | `a569175c043990f9598e3db8e0329694975c27b01a0deb1ec8762595781f41dc` |

The manual custody archive contains reports and reconciliation controls. It does
not contain the original bounded API envelopes. Those envelopes carry stable
provider IDs, versions, line payloads, relationship IDs, and acquisition
provenance. Native admission must retrieve the original envelope store and prove
its bounded-snapshot digest; reconstructing transactions from report rows is not
an acceptable substitute.

## Exact admission prerequisites

1. Retrieve the original read-only bounded-envelope store for the source run.
   Verify the source manifest and bounded-snapshot hashes above, file custody,
   record count, family counts, relationship count, provider realm/company
   binding, cutoff, and zero-count family observations.
2. Restore a candidate-bound database backup into a disposable isolated target.
   Verify the schema head, tenant identity, runtime database restrictions, and
   initial inventory digest. The rehearsal target must have no route to QBO or
   bank-feed mutations.
3. Apply all 20,702 envelopes only to the source disposition ledger. Each record
   must be `BOUND`, `QUARANTINED`, `UNSUPPORTED`, or
   `PROVIDER_UNAVAILABLE`; unexplained loss is not allowed. This phase creates
   no journal, invoice, payment, balance, or bank transaction.
4. Approve an exact 131-account crosswalk. Every account needs source identity,
   parent, active state, currency, statement classification, normal balance,
   control-account role, and native target. Names alone are not identities.
5. Approve historical native contracts for Customer, Invoice, Payment,
   Deposit, Purchase, Transfer, Refund, and Journal behavior. Contracts must
   preserve effective dates, lines, source versions, branch/tenant scope,
   double-entry semantics, source idempotency, and overlap detection.
6. Reconcile the 253 existing native invoices and 258 native payments using
   exact source IDs or explicit reviewed bindings before creating historical
   records. No name, amount, date-proximity, or fuzzy match may create a link.
7. Accept a deterministic A/R bridge from invoice open balances of
   `$500,584.34` to Balance Sheet A/R of `$399,782.43`. The `$100,801.91`
   difference, `$87,544.91` provider-unapplied amount, 73 unlinked payments
   totaling `$85,414.91`, `$2,130.00` unapplied-versus-unlinked difference, and
   remaining `$13,257.00` must remain explicit until accountant disposition.
8. Build per-account opening and historical journal controls. Each line needs a
   source artifact and row/record identity. The opening must balance without a
   plug; unresolved A/R, cash, bank, card, payroll, tax, or other control
   balances cannot be coerced to zero.
9. Use distinct prepare, Finance-approve, and post authority through the native
   journal lifecycle. Posting remains separately authorized and is outside this
   packet.
10. Reproduce native General Ledger, Trial Balance, Balance Sheet, Profit and
    Loss, and receivables reports for the same cutoff/basis. Require stable
    report checksums, source-parity accounting, tenant isolation, and exact
    drill-down provenance.

## Admit versus hold

### Safe now

- Preserve all 20,702 sealed records and 97,093 relationships as source
  evidence.
- Once the original envelopes are in verified custody, register every record in
  the source disposition ledger as an exact binding or explicit hold. This is
  not a financial posting.
- Preserve the 1,171 exact Payment-to-Invoice links and the fact that none point
  to a missing source Invoice. These relationships remain conditional until the
  Invoice/Payment native contracts and Customer mappings are approved.
- Preserve 33 balanced source JournalEntry entities (84 API posting lines) and
  the 12 bounded zero-count families as evidence. Neither is opening-balance or
  posting authority.

### Held from native Accounting

| Population | Count/amount | Required release condition |
|---|---:|---|
| Chart accounts | 131 | Exact mapping and Finance classification |
| Invoices | 1,341 / `$500,584.34` open | Customer mappings, native contract, overlap control, A/R bridge |
| Payments | 1,237 | Native contract and application/cash controls |
| Unlinked payments | 73 / `$85,414.91` | Explicit unapplied-cash/customer-credit disposition; never fabricate Invoice links |
| Purchases, deposits, transfers | 15,885 | Native double-entry contracts and duplicate prevention |
| General Ledger/opening | all financial lines | Per-account controls, complete mappings, balanced opening, Finance approval |
| American Express pending feed | 102, including 4 exact repeats | Stable identity/matching and separate posting authorization |
| Payroll | 30 Employees and all payroll exports | Separate payroll authority and coverage reconciliation |

There are currently zero native Accounting control rows in the captured
inventory (accounts, source identities, banks, bank transactions, journals,
posting sources, QBO application records, review items, decisions, vendors, and
vendor mappings). Consequently, no source record is automatically eligible for
native financial posting today.

## Seven preserved conflicts

1. `D-001`: five General Ledger presentation rows; amount difference `$0.00`.
2. `D-002`: A/R bridge difference `$100,801.91`.
3. `D-003`: 73 unlinked Payments totaling `$85,414.91`; provider unapplied
   `$87,544.91`.
4. `D-004`: 102 unposted AmEx rows, including four exact repeats; automatic
   posting and deduplication prohibited.
5. `D-005`: payroll coverage differences of `$41,734.39` gross and `$35,846.00`
   net.
6. `D-006`: the Accounting OAuth scope does not provide detailed Payroll data.
7. `D-007`: preserved evidence has not been admitted into native structures.

The planner fails if any disclosed conflict disappears, duplicates, changes
identity, if a source count drifts, if a financial control develops a nonzero
variance, or if the predecessor rehearsal reports a write.

## Disposable qualification sequence

1. Start a disposable PostgreSQL 16/Redis 7 target on loopback-only endpoints.
2. Migrate from an empty database to the current single head.
3. Restore a synthetic pre-admission backup and prove its digest/inventory.
4. Replay representative sealed envelopes through the native disposition
   service. Verify exact bindings, individual quarantine, unsupported-family
   accounting, source parity, idempotent replay, and cross-tenant denial.
5. Reconcile a synthetic balanced opening package through the native opening
   service. Verify missing evidence and conflicting mappings fail closed.
6. Post only synthetic eligible opening facts using three distinct test actors;
   verify Trial Balance and Balance Sheet consumption and deterministic report
   checksums.
7. Roll the disposable target back and prove zero committed admission rows.
8. Rerun static gates and the focused source-admission, native-opening, and
   financial-reporting suites.

This proves the process, not the correctness of unresolved All County balances.
The real source remains blocked before native writes until the envelope custody,
mapping, contract, reconciliation, and Finance-authority gates above are met.

### Executed qualification

The focused process proof ran against disposable loopback-only PostgreSQL 16 and
Redis 7 with ACLs. It migrated an empty database to the single Alembic head
`x3y5z7a9c1e4`, reported no schema drift, passed 49 focused tests, and verified
cleanup of the disposable database and cache. The executed coverage included:

- sealed-plan determinism and custody/count/control tamper rejection;
- all-seven-conflict preservation and the zero-write boundary;
- native source disposition, exact binding, quarantine, source parity, and
  idempotent replay;
- opening-package validation, fail-closed missing/conflicting evidence,
  distinct-actor enforcement, native posting lifecycle, and idempotency;
- Trial Balance and Balance Sheet consumption of synthetic eligible opening
  facts with deterministic report checksums;
- pre-existing Accounting-admission packet controls.

Ruff, Ruff format, and focused MyPy checks pass. No QBO operation, protected
database write, bank-feed post, Payroll action, or actual transaction posting
occurred.

The separate release-database recovery harness also passed on an internal-only
network: 430 objects from pristine UTF-8 PostgreSQL 16, custom-format backup and
manifest verification, empty-target restore at `x3y5z7a9c1e4`, preserved probe
data, transactional failure rollback, clean-target recovery after simulated
partial execution, re-upgrade, healthy readiness, no host ports, and verified
resource cleanup. This is disposable recovery qualification, not a backup of
protected All County financial state.

## Backup and rollback

Before an authorized admission, take a candidate-bound database backup, write a
SHA-256 receipt, restore it in isolation, and record schema/inventory/source
parity. Use phase-bound idempotency keys and immutable receipts. If an executed
phase fails, restore the verified pre-admission backup. Never roll back by
deleting posted journals, rewriting source evidence, or changing expected
control hashes. Re-verify schema head, inventory digest, tenant isolation, and
native report checksums after restore.

## Next executable action

Retrieve the original bounded-envelope evidence store through approved custody,
verify `e4d672c1cdfca858e4a8e923a51a86627753c7ea1fedc695daa98066a5dc6041`,
and run disposition-only application in the disposable database. Native chart,
subledger, opening, or ledger writes remain unauthorized until their respective
gates are accepted.

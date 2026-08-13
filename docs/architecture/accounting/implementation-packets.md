<!-- markdownlint-disable MD013 -->

# Internal Accounting Implementation Packets

## Common execution boundary

All packets target `ACP-Enterprise` from a freshly fetched
`origin/customer-management-v1` in a unique isolated worktree. Each is `TYPE B`.
Implementation may run in parallel only with disjoint files; migration and shared
financial-contract integration is serialized. Every packet stops for schema
scope outside its authority, policy ambiguity, security/data-integrity concern,
or semantic integration conflict.

Common allowed roots are the packet-specific roots below plus matching focused
tests and explicitly named shared event/permission seams. Common prohibited roots
are `.env*`, credentials/private keys, deployment/Production configuration,
Migration workstream code, Economics, Mission Control/worker control, and
unrelated domains. No packet authorizes Preview, Production, import, cutover,
force-push, or irreversible operations.

Starting commit rule for every packet: fetch immediately before workspace
creation, record the full origin SHA, require zero behind, and stop for any
non-mechanical overlap. Proposed branches are
`work/acc-core-contract-1`, `work/acc-core-1`, `work/acc-ar-contract-1`,
`work/invoice-1-3-accel`, `work/pay-1-3-accel`, `work/acc-ap-1`,
`work/acc-post-1`, `work/acc-rpt-1`, `work/acc-data-1`, and
`work/acc-mig-1`, respectively. Branch names do not authorize Start.

Every runtime packet validates Ruff, MyPy, focused and affected regressions,
authorization and Company/Branch isolation, transaction rollback, idempotency,
audit, fresh Alembic upgrade, downgrade/re-upgrade, drift, exactly one head,
`git diff --check`, and a focused secret scan. Frontend changes also require tests,
ESLint, typecheck, and production build.

Parallel lane ownership, successor gates, and actual integration evidence are
controlled by the [Accounting integration control](integration-control.md) and
its [durable ledger](accounting-integration-ledger.json). Packet order alone is
not readiness or Start authorization.

## Packet ledger

| Packet | Dependencies and exact scope | Enforceable paths | Persistence and integration | Gates and completion |
| --- | --- | --- | --- | --- |
| `ACC.CORE.CONTRACT.1` | [Core ledger contract](core-ledger-contract.md); freeze COA/GL/journal/period/reversal/audit/SOD interfaces without runtime | `docs/architecture/accounting/**`, new Accounting product specification only | No migration; precedes all Accounting runtime | Architecture tests and links; owner accepts; then `ACC.CORE.1` may start |
| `ACC.CORE.1` | Accepted [core ledger contract](core-ledger-contract.md); implement accounts, stable source mapping, balanced journals, periods, reversals, audit, Finance permissions | Exact [machine boundary](acc-core-1-execution-boundary.json) | Owns Accounting migration slot 1; first integration after current head | Finance control review; no Preview/Production; stop at owner review |
| `ACC.AR.CONTRACT.1` | [AR/Invoice contract](accounts-receivable-invoice-contract.md); freeze invoice/AR/tax/credit/correction/aging-input rules without runtime | Accounting/Financial architecture and product specifications plus focused contract tests only | No migration; may run with core contract | Contract acceptance; accelerated invoice packet becomes eligible for owner Start |
| `INVOICE.1-3.ACCEL` | [Machine packet](invoice-1-3-accel.packet.json), accepted estimate/job contracts; invoices, AR, tax, credits, voids, adjustments, corrections, aging facts | Packet-defined new Invoicing backend/frontend roots and narrowly required registration, event, permission, and migration seams | Owns Accounting migration slot 2; serialize after `ACC.CORE.1` | Deterministic totals, balancing handoff, tax, corrections, concurrency, UI/security; Finance review |
| `PAY.1-3.ACCEL` | Accepted invoice contract and current processor decision; payment application, refunds, failures, deposits, clearing, undeposited funds, settlement reconciliation | new `backend/app/payments/**`, `backend/tests/payments/**`, matching frontend seams, narrowly required events/permissions | Owns slot 3; no processor replacement or secrets | Provider fakes/contracts, replay/webhook/idempotency, duplicate-charge and settlement tests; Finance review |
| `ACC.AP.1` | Accepted [AP/vendor contract](accounts-payable-vendor-contract.md); vendors, bills, credits, AP balances/aging facts, controlled disbursement recording | Exact [machine packet](acc-ap-1.packet.json) | Owns slot 4 after slot 3; Purchasing integration is contract-only unless separately approved | AP control/balance, duplicate bill, reversal, aging, SOD/security; Finance review |
| `ACC.POST.1` | Accepted core, invoice, payment, and AP contracts; idempotent Business Event/domain fact to journal posting, tax, inventory-control, payroll-summary interfaces | `backend/app/accounting/**`, focused producer adapters/tests, named `backend/app/events/**` seams only | Owns slot 5 if required; no direct cross-domain table writes | Exactly-once/replay, source mapping, failure queue, balanced posting and producer rollback; serialized integration |
| `ACC.RPT.1` | Accepted postings; trial balance, balance sheet, income statement, GL detail, AR/AP aging | new `backend/app/financial_reporting/**`, tests, matching frontend reporting seams; read-only Accounting interfaces | Owns slot 6 if projection persistence is required | Rebuild/freshness, control-account ties, date/period basis, tenant security, statement balance; Finance acceptance |
| `ACC.DATA.1` | [QuickBooks exit data contract](quickbooks-exit-data-contract.md); define source inventory, formats, ownership, checksums, disposition and workpapers | `docs/architecture/accounting/**`, new sanitized schemas/fixtures under `docs/project/accounting-cutover/**`; never real exports | No migration/import; may run parallel after this contract | Schema/fixture/checksum/reconciliation validation; owner prepares; Finance reviews later |
| `ACC.MIG.1` | Accepted `ACC.DATA.1`, its [manifest schema](../../project/accounting-cutover/schemas/acc-mig-1-input-manifest.schema.json), [runtime foundation](acc-mig-1-runtime-foundation.md), and all target schemas; deterministic opening-state loader, rejects, dispositions, replay, control report | `backend/app/accounting_migration/**`, tests, sanitized fixtures; no customer Migration workstream modification without separate authority | Provider-neutral synthetic foundation is migration-free; any persistence owns slot 7 after all predecessors; import execution is TYPE C and separate | Fresh/synthetic loads, replay, counts, exact controls, teardown; Preview/Production import forbidden until separately approved |

## Accounting migration serialization

The inspected authoritative head at this contract's start is `u6k8f0h2j497`.
Immediately before every integration, fetch origin and determine the then-current
single head. The intended order is:

`ACC.CORE.1 → INVOICE.1-3.ACCEL → PAY.1-3.ACCEL → ACC.AP.1 → ACC.POST.1 → ACC.RPT.1 → ACC.MIG.1`.

The order is migration ownership, not an instruction to create unnecessary
migrations. A packet with no schema change consumes no revision. Whichever
migration integrates next must descend from the current authoritative head and
be fully revalidated. Sibling heads, silent re-parenting, force-push, and unjustified
merge migrations are prohibited.

## Readiness at contract completion

`ACC.CORE.CONTRACT.1` is complete at `c3717fa`; consequently `ACC.CORE.1` is
dependency-ready but still requires its own owner Start. `ACC.AR.CONTRACT.1` is
complete at `0d6e796`; consequently isolated `INVOICE.1-3.ACCEL` implementation
is dependency-ready for separate owner Start, while its migration integration
must follow `ACC.CORE.1`. `ACC.DATA.1` has a clean worktree but no implementation
evidence. No other runtime packet is READY until the dependency and metadata
conditions in the integration control are satisfied.

# Customer integration wave preflight 1

Observed protected authority: `d4eee6f6b0bc178d58654f26f3ef2b9429332ab3` on 2026-09-12.

This packet is integration analysis only. It performs no protected merge, deployment, source mutation, Customer communication, Accounting posting, or money movement.

## Candidate classification

| Candidate | Head | Classification | Disposition |
|---|---|---|---|
| Customer roster/search/detail | `608861cbdb3c` | `INTEGRATED` | Patch-equivalent protected commit `42a4f680`; do not merge the old branch. |
| Preferred-contact roster projection | `95594f1cbf99` | `INTEGRATED` | Patch-equivalent protected commit `b22297c6`; do not merge the old branch. |
| Customer office navigation acceptance | `5f3e66b0248a` | `INTEGRATED` | Squash-integrated as protected commit `e9377e72`; do not merge the old branch. |
| Customer office UX reliability | `5a662b93cdc8` | `INTEGRATED` | Squash-integrated as protected commit `d50b47a3`; do not merge the old branch. |
| UX reliability reconciled | `8516b08b1fbd` | `SUPERSEDED` | Merge-only reconciliation branch; protected already contains its material feature commit. |
| Customer-to-cash completion | `5f13f54ede40` | `SUPERSEDED` | Old branch contains only a non-authoritative import-style change beyond its merge base. |
| Customer office operating acceptance 2 | `12ade09412eb` | `RECONCILE_REQUIRED` | Do not insert into this wave. It conflicts in `CustomerDetailView.tsx`, `CustomerOperationsPanel.tsx`, and `useCustomers.ts` after the workflow/AR chain; unique related-history pagination should be reviewed as a bounded successor after the core wave lands. |
| Customer office workflow | `da23d1f38222` | `READY_TO_INTEGRATE` | First remaining branch; contributes `60eab41c`, then `da23d1f3`. |
| Customer service/AR operating acceptance | `60457cbb3a45` | `READY_TO_INTEGRATE` | Requires workflow head; contributes `f583bc37`, then `60457cbb`. |
| Customer source evidence classification | `cd0bb0fe6fe1` | `RECONCILE_REQUIRED` | Requires AR head. Product merge is clean, but protected reliability tests require the four-line mock/assertion reconciliation below before qualification. |

## Exact integration order

1. Start from current protected authority and preserve protected commits `42a4f680`, `b22297c6`, `e9377e72`, and `d50b47a3`.
2. Integrate `work/customer-office-workflow-1` through `da23d1f3822289f552d2efd133adbddce8224948`.
3. Integrate only the successor commits on `work/customer-service-ar-operating-acceptance-1`: `f583bc379eeeb3af9b1b63b858d009ceaf00ffc1`, then `60457cbb3a455885d0bc6ec6d915f52125baabfd`.
4. Integrate `cd0bb0fe6fe1fec7ce8317a9409159c59283fb93` from `work/customer-source-evidence-classification-1`.
5. Reconcile protected `CustomerOperationsPanel.reliability.test.tsx`: mock `useInvoiceWorkspace` and `useCustomerBalance` rather than obsolete `useInvoices`, expect the separate “No current Jobs…” copy, and expect the current “Related work is partial” / “Customer identity remains usable” copy.
6. Run the gates below. Do not merge `12ade094` into this sequence.

A synthetic merge of protected authority plus `cd0bb0fe` produced no textual merge conflicts. Before the test-only reconciliation it exposed exactly two stale protected reliability-test failures. With the reconciliation applied, 8 affected frontend files / 50 tests pass and the production frontend build passes. The merged PostgreSQL Invoice/AR/source-classification suite passes 11 tests.

## Customer product acceptance matrix

| Case | Expected truth | Automated/pre-deploy gate | Authenticated Preview gate |
|---|---|---|---|
| Name, phone, address/location search | Server-filtered admitted Customer population; never first-page inference | Customer API/management tests | Search a known admitted identity independently by each supported field. |
| One Location | Exact native Customer/Location relationship | Customer detail fixtures | Open Location and preserve Customer context into Job creation. |
| Multiple Locations | Distinct admitted Locations; no collapse | Detail fixtures | Open each Location and verify correct Job preselection. |
| No current Job | Native empty state, not proof of no source history | Operations reliability/workflow tests | Confirm history remains visible if present. |
| Current/open Job | Current lifecycle group and direct Job navigation | Workflow tests | Open Job, existing scheduling control, and return without re-search. |
| Historical Jobs | Completed/cancelled separated from current | Workflow tests | Reconcile against customer-filtered paginated Jobs route. |
| Appointments | Bounded window and exact Appointment link | Workflow tests | Open Appointment/Scheduling and preserve Customer context. |
| Partial related work | Customer identity remains usable; missing section not “none” | Reliability/workflow tests | Fail one sanctioned fixture/API boundary and retry safely. |
| Stale source projection | Visible stale state only from source contract | Reliability fixtures | Compare source as-of to accepted Migration evidence. |
| Held/source-only | Visibly non-native and non-selectable | Management readiness fixtures | Reconcile held counts/identities to Migration admission packet. |
| Backend unavailable/retry | Safe generic failure; no raw error or fabricated empty result | Reliability fixtures | Exercise sanctioned failure and successful refresh. |
| Missing optional contact | Stable unavailable copy; no fabricated value | Detail tests | Verify Customer remains operable without phone/email. |
| Native Invoice and AR | Current native Invoice/ledger authority only | Invoice AR tests | Match Invoice count, open balance, currency, and as-of. |
| Applied payment | Applied only through accepted application evidence | Invoice AR tests | Confirm it reduces the linked Invoice obligation. |
| Unapplied receipt | Separate Customer receipt/credit evidence | Workflow/source tests | Confirm it is not displayed as an Invoice payment. |
| Current evidence | `CURRENT_AUTHORITATIVE` only for native scoped evidence | Classification tests | UI says current ACP evidence. |
| Historical evidence | Only through accepted Customer source identity | Classification tests | Match acquisition/digest out-of-band to Migration packet; UI hides IDs/digests. |
| Stale / partial / conflicting | Explicit independent classifications; never inferred complete/current | Classification and UI parameterized tests | Exercise an authoritative example of each. |
| Unavailable / no balance evidence | No source identity, amount, date, or digest fabricated; no zero inferred | Classification/workflow tests | Verify no zero balance is displayed as evidence. |

## SOURCE.4 and real-data dependency

Migration owns identity matching, admission, held/conflict disposition, freshness, and accepted source digests. The Customer wave consumes those facts. Acquired files or global QBO/HCP projections alone do not authorize a Customer-scoped historical classification.

After Migration publishes its accepted Preview admission packet, record deployed SHA, Company/Branch, admission/package digest, source and acquisition dates, admitted/held/conflicting counts, and the selected Customer/Location/Job/Appointment/Invoice identities. Execute the matrix above with real admitted non-Production records. Any missing crosswalk or source fact remains held, partial, conflicting, stale, or unavailable; it must not be repaired by frontend inference.

## Qualification and post-deploy commands

After step 5, run from the integrated repository:

```sh
cd frontend
npm test -- --run src/components/customers src/hooks/useCustomers.test.tsx src/routes/JobsRoute.customer-context.test.tsx src/routes/InvoicesRoute.test.tsx
npm run lint
npm run build

cd ../backend
pytest -q tests/invoicing/test_customer_source_classification.py tests/invoicing/test_invoice_ar.py
ruff check app/invoicing tests/invoicing
mypy app/invoicing app/customer_migration app/customers
```

Enterprise deployment verification, using its protected local environment file and Preview URL:

```sh
PREVIEW_URL="${ACP_PREVIEW_URL}" ./scripts/verify-preview.sh "${ACP_PREVIEW_ENV_FILE}"
```

After SOURCE.4 admission and Preview clearance, run the existing read-only gate with protected input/output paths (never source rows or secrets on the command line):

```sh
cd backend
python -m scripts.crossdomain_post_source4_acceptance --input "${ACP_ACCEPTANCE_INPUT}" --output "${ACP_ACCEPTANCE_OUTPUT}"
```

Then perform the authenticated UI matrix. Record evidence, but do not call a screenshot alone acceptance.

## Schema and gates

The workflow and AR commits are frontend-only. Source classification extends an existing response and adds no migration. Fresh zero-to-head PostgreSQL migration succeeded on the candidate lineage. Real-data acceptance remains gated by accepted SOURCE.4 admission and authenticated Preview deployment. QBO live-source availability is not inferred and is not required for fixture-backed integration qualification.

## Protected integration watch

At `2026-09-12T19:17:02Z`, protected authority advanced from `d4eee6f6` to `ccf1228aafd9b6291f946b07756f8e031b1db94d` through Scheduling recovery PR #250. The four Customer-wave commits remain pending.

This advancement creates one real integration conflict in `frontend/src/routes/JobsRoute.tsx`. Reconciliation must preserve protected authority's `hasCustomerContext`, Customer and Service Location filtering, “Customer work context” notice, and “Show all Jobs” recovery. It must also preserve the Customer candidate's explicit return link to `/customers/{customerId}`. Do not choose the older candidate query because it omits protected `serviceLocationId` filtering.

The earlier reliability-test reconciliation remains required. No backend/schema conflict was introduced by this protected advancement.

At `2026-09-12T19:19:35Z`, protected authority advanced again to `36fe3eeaa85905ef282b07ea8b7cc5482c335794` through Payroll operating-wave PR #251. This is semantically unrelated: all four Customer commits remain pending and the single `JobsRoute.tsx` reconciliation above is unchanged.

At `2026-09-12T19:35:00Z`, protected authority is `96d67cb73dbe4838e882e1551de5906eda598f4e` after guarded current HCP overlay PR #253. The Customer commits remain pending. `CUSTOMER.CURRENT.AUTHORITY.RECONCILIATION.1` is pushed as `work/customer-current-authority-reconciliation-1` at `d67125426ab4427c634c836500790407d3941f9c`.

Enterprise should integrate that reconciliation branch as the replacement for individually applying the queued Customer chain. It contains the required precursor and all four Customer-wave semantics, preserves protected Customer and Service Location Job filtering, the protected Customer-context notice and **Show all Jobs** recovery, adds **Return to Customer**, and includes the bounded reliability-test reconciliation. Do not also integrate `customer-office-operating-acceptance-2`.

Qualification on the reconciled current-authority branch: 123 frontend files / 466 tests passed; affected Customer/Invoice/AR set 8 files / 50 tests passed; PostgreSQL Invoice/AR/source classification 11 tests passed; fresh zero-to-head PostgreSQL upgrade reached the single head `e5g7i9k1m3o5`; ESLint, production TypeScript/Vite build, changed-boundary Ruff, MyPy (56 files), Python compilation, and diff check passed. A broader Ruff scan also reported one inherited import-order issue in untouched `tests/invoicing/test_financial_list_boundaries.py`; it is not introduced by this candidate.

Protected authority then advanced to `09e73da69a5323f04133a2d6a031804c76861e66` through Payroll Employee-readiness PR #254. That authority was merged without conflict into the Customer reconciliation candidate, now `da2df882cf46fc9ccb7653a1982960f2b61d3277`. Post-merge qualification again passed the affected 50 frontend tests, production frontend build, 11 PostgreSQL Invoice/AR/source-classification tests, Ruff, and MyPy. The earlier failed backend invocation was an environment-only run without its PostgreSQL network (`postgres` did not resolve); the supported isolated PostgreSQL rerun passed all 11 tests.

Protected authority next advanced to `52dc336766a67fc0c4698244b9894bab0fe65913` through Identity account-recovery PR #256. It merged without Customer conflict; the reconciliation candidate is now `174fcd4e8a040875f0b8f12e4516f4c42f1a1a12`. The focused 50 Customer/frontend tests and diff check pass, and the protected Identity migration advances the single Alembic head to `f6h8j0l2n4p6` without a Customer migration.

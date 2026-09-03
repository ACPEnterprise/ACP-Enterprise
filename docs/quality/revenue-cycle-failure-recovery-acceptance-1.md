# Revenue Cycle failure/recovery acceptance 1

## Authority and safety boundary

- Protected authority: `7d12ffeec1ff6de2f0a7dcfee8ba8e899bf71e6c`.
- Isolated branch: `work/revenue-cycle-failure-recovery-acceptance-1`.
- Synthetic identities and the deterministic fake provider were used. No real
  Payment, refund, settlement, communication, Accounting posting, Preview
  mutation, or Production action occurred.

## Acceptance result

| Surface | Failure/recovery result |
| --- | --- |
| Invoice workspace | Bounded errors remain operator-safe; empty and unavailable remain distinct. |
| AR and Customer balance | Partial detail failure is explicit and never presented as zero. Stale versions fail closed. |
| Payment evidence | Capture assertion remains distinct from settlement and cash. Provider response loss now persists `reconciliation_required`. |
| Application evidence | Duplicate/replay is idempotent; contradictory or stale application fails closed without rewriting prior evidence. |
| Settlement/funds in transit | Variance creates reconciliation evidence. No UI or API infers funds movement from intent, receipt, application, or deposit evidence. |
| Receipts | Receipt detail explicitly states that capture evidence does not prove settlement, deposit, or bank cash. |
| Statements | Native statement artifact/delivery authority remains partial and was not invented by this milestone. Customer balance facts remain bounded native evidence. |
| Provider unavailable | Timeout/exception after submission becomes deterministic uncertainty with a safe evidence digest; same-key replay does not call the provider again. |

## Defects repaired

1. **P1 — provider exception escaped the collection boundary.** An exception or
   response loss after provider submission could leave a durable created intent
   while surfacing an uncontrolled server error. The boundary now records one
   ambiguous attempt, marks the intent `reconciliation_required`, opens the
   existing reconciliation exception, excludes raw provider details, and
   prevents replay from resubmitting.
2. **P1 — partial Revenue Cycle evidence looked complete.** Failed Payment,
   Invoice-office, or Customer-balance refreshes could be omitted or treated as
   empty. The affected screens now say evidence is unavailable/stale and that an
   unavailable queue is not zero.
3. **P1 — mutation failure recovery was not presented.** Collection,
   application, and refund failures now use the shared safe operator error
   translator and direct refresh/reconciliation. Promise rejection is retained
   by the query mutation rather than escaping the event handler.
4. **P2 — collection wording overstated completion.** The action is now
   “Submit to provider,” and its copy states submission is evidence, not
   settlement or bank cash.

## Deterministic scenarios exercised

- captured, declined, failed, ambiguous, timeout/response loss;
- identical and contradictory idempotency replay;
- concurrent duplicate collection, application, and refund commands;
- stale Invoice and receipt versions, over-application, and foreign scope;
- incomplete AR/Customer balance and failed UI refresh;
- settlement replay and variance/reconciliation;
- duplicate and contradictory webhook evidence;
- accounting posting-receipt replay without performing a posting.

No raw provider exception, endpoint, credential, SQL detail, opaque method, or
backend diagnostic is reflected to operators or generic lifecycle evidence.

## Qualification

- Fresh PostgreSQL migration to head `n0p8r16g3t9u`: passed.
- Affected backend: 104 passed; four existing SQLAlchemy transaction cleanup
  warnings, no failures.
- Full frontend: 108 files / 368 tests passed.
- Targeted frontend Revenue Cycle/Payments: 3 files / 8 tests passed.
- ESLint, TypeScript production build, Ruff, MyPy, Python compilation, and
  `git diff --check`: passed.
- Frontend dependency audit: zero vulnerabilities.

## Remaining external gates

- A real payment provider and merchant account are not admitted.
- Provider-specific timeout classification, lookup/reconciliation, webhook,
  settlement, payout, dispute, refund, and test-mode contracts require provider
  selection and credentials.
- Real funds-in-transit/bank settlement truth remains unavailable until admitted
  provider evidence exists; it must never be inferred.
- Customer-facing receipt and statement artifact/delivery authority remains a
  separate product/provider/Communications gate.
- Credit, write-off, dispute/hold, collections, correction, statement, and
  receipt policies retain their recorded owner/policy gates.

Enterprise may integrate this branch against then-current protected authority
and rerun the listed intersections. This lane performs no deployment.

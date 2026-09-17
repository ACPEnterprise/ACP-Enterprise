# Connected assistant night-shift ledger

Lane: Laptop-A  
Protected starting authority: `63e4ac863763e00a3090e172a43fc32e5feb17da`

This ledger records continuous acceptance findings. A pushed checkpoint is not
a stop condition. Source domains continue to own their facts and calculations.

## Owned defect ledger

| ID | Workflow | Defect | Severity | Disposition |
| --- | --- | --- | --- | --- |
| LIA-N1-001 | Contextual Customer → Scheduling follow-up | The URL entity context overrode the server-confirmed topic switch on every later request | BLOCKS_WORK | Repaired with route-generation-bound conversation context and browser regression coverage |
| LIA-N1-002 | May → June → compare them | The web request contract discarded backend temporal context | BLOCKS_WORK | Repaired by carrying the complete resolved temporal contract through the next request |
| LIA-N1-003 | Period comparison | Answer composition collapsed two same-domain evidence packets and could present one period as a comparison | BLOCKS_WORK | Repaired with explicit period-A and period-B summaries and no fabricated delta |
| LIA-N1-004 | Direct named Payroll question | “Is [Employee] ready for Payroll?” returned aggregate Payroll evidence instead of resolving the Employee | BLOCKS_WORK | Repaired with exact authorized Employee resolution and Employee-specific Workforce + Payroll retrieval |
| LIA-N1-005 | Spoken/natural Job and navigation | “Show me job three thirteen” and “Open Lianne” did not enter exact subject resolution | SLOWS_WORK | Repaired without number-word conversion or fuzzy identity matching |
| LIA-N1-006 | Default owner briefing | “Today” forced Beacon/current readiness through unsupported historical filtering | BLOCKS_WORK | Default briefing now requests current state; explicit dated questions remain period-bound |
| LIA-N1-007 | Voice payment questions | Read-only “what did they pay/collect?” wording was classified as money mutation | SLOWS_WORK | Mutation recognition now requires an imperative at the start of the utterance |
| LIA-N1-008 | Request failure | UI reduced authentication/connectivity/conflict failures to one generic message | SLOWS_WORK | Uses the established safe operator-error classifier; still infers no answer |
| LIA-N1-009 | Malformed contextual link | An invalid record identifier was silently discarded, leaving the user to believe record context was active | SLOWS_WORK | Fail visibly before asking; the untrusted identifier is not sent to LIA |
| LIA-N1-010 | Evidence inspection | Exact Appointment, Invoice, and Payment evidence navigated only to collection pages | SLOWS_WORK | Uses the existing authorized detail routes when an evidence entity identity is present |
| LIA-N1-011 | Job follow-up | A question containing “Job JOB-000306” outside the narrow “show/open” form lost exact subject resolution | BLOCKS_WORK | Extracts the explicit canonical Job reference without fuzzy matching |
| LIA-N1-012 | Brief answer mode | “Short version” could return a complete long owner-answer line | ANNOYING | Deterministic, word-safe 320-character presentation cap; evidence metadata remains intact |
| LIA-N1-013 | Voice conversation timeout/cancel | Inactivity could label the session IDLE without aborting active recognition; Cancel did not end every capture/speech path | BLOCKS_WORK | Inactivity and Cancel now abort recognition, cancel speech, clear timers, and exit conversation mode |
| LIA-N1-014 | Exact Price Book lookup | “What’s our price for drain cleaning?” routed to Price Book but returned catalog status counts instead of the authorized current customer price | BLOCKS_WORK | Added exact name/code, selected-Branch retrieval over the authoritative catalog pointer; ambiguous/no-match/Branch-missing cases fail closed and costs remain excluded |
| LIA-N1-015 | Operational record lookup | Natural Estimate, Invoice, and Appointment references were classified by domain but degraded to company/Branch aggregate counts | BLOCKS_WORK | Canonical `EST-`, `INV-`, and `APT-` references now resolve exactly inside current Company/Branch permission scope; foreign and unknown identities remain hidden |
| LIA-N1-016 | Named Employee time/Dispatch context | Named Employee period questions dropped Timekeeping/Dispatch after identity resolution, while generic retrieval compared the Employee UUID to the evidence-record UUID | BLOCKS_WORK | Preserve the permitted Employee-related domains and filter accepted Timekeeping revisions/primary Dispatch assignments by their Employee columns |
| LIA-N1-017 | Invoice → Payment follow-up | Asking for payment evidence from an exact Invoice context switched to unscoped Company-wide Payment counts | BLOCKS_WORK | Fail incomplete with direct Invoice navigation until Revenue Cycle provides the Invoice application/settlement projection; broad Payment evidence is never substituted |
| LIA-N1-018 | Appointment assignment question | Exact Appointment resolution discarded Dispatch and could only report Appointment state, not the authoritative assignee | BLOCKS_WORK | Compose the existing permission-scoped Dispatch detail read model by Appointment identity, including truthful unassigned state and existence hiding; no assignment mutation is exposed |
| LIA-N1-019 | Financial amount wording | Amount questions could reach record-count/readiness evidence whose state did not contain an authoritative monetary aggregate | BLOCKS_WORK | Amount questions now fail incomplete unless an admitted posted-ledger amount authority is present; counts are never presented as dollars and invoice/payment/settlement/cash/revenue semantics remain distinct |
| LIA-N1-020 | Ambiguous owner financial language | “What did we make?” had no bounded source and returned a generic unavailable response, while “sales” could be treated as ordinary readiness evidence | SLOWS_WORK | Ask the owner to choose invoiced amount, earned revenue, collected cash, QuickBooks income, net income, or contribution; sales/revenue/income/profit amount wording also requires authoritative monetary evidence |
| LIA-N1-021 | Contextual Beacon explanation | A selected Beacon signal ID survived in response context, but retrieval ignored it and summarized the entire attention queue for “Explain this one” | BLOCKS_WORK | Exact Beacon context now selects only the currently authorized signal and returns its accepted explanation, severity, priority, recommendation, evidence digest, and scope; unknown/foreign identities reveal nothing |

## UI friction ledger

| Screen | Intended task | Observed friction | Expected behavior | Severity | Surface | Safe now / later |
| --- | --- | --- | --- | --- | --- | --- |
| Ask LIA | Ask a question after arriving from a record | Route context could never yield to an explicit new topic | Server-confirmed topic becomes the next bounded context | BLOCKS_WORK | Desktop/mobile | Fixed now |
| Ask LIA | Compare business periods | Period disappeared between browser turns | Preserve dates, timezone, basis context, and prior period | BLOCKS_WORK | Desktop/mobile/voice | Fixed now |
| Ask LIA | Understand a service failure | Generic “request unavailable” supplied no recovery distinction | Safe authentication/connectivity/conflict language | SLOWS_WORK | Desktop/mobile | Fixed now |
| Ask LIA | Reach the answer quickly | Readiness/foundation/briefing content precedes the question and can be long on phones | Consider a later task-first information hierarchy after owner visual acceptance | ANNOYING | Mobile | UX re-imagine; no speculative redesign tonight |
| Luminary / Economics | “Ask LIA about this evidence” | Existing entry points do not bind a finding/result identifier | Pass an accepted opaque source context or use honest generic wording | SLOWS_WORK | Desktop/mobile | Active Intelligence presentation ownership; handoff |

## Cross-domain contract handoffs

- Scheduling/Dispatch: bounded ordered record references are required for “the
  first appointment,” assignment drill-back, and exact cross-view navigation.
- Price Book current price: closed after protected authority exposed the same
  active-version pointer used by the operator catalog. LIA now consumes that
  read model with exact identity and selected-Branch scope; historical charge,
  cost, and margin questions remain owned by Revenue Cycle/Economics.
- Revenue Cycle: Invoice/Payment relationship, application, settlement, cash,
  historical-as-of evidence, and authoritative monetary aggregates require
  domain-owned projections. LIA explicitly refuses to turn record counts into
  dollars while those projections are absent.
- Timekeeping: Employee/period accepted interval and hours evidence requires a
  Timekeeping-owned total-hours projection; LIA now retrieves the correct
  Employee's accepted revisions but explicitly refuses to present revision
  counts or scheduled duration as worked/paid hours.
- Luminary/Economics presentation: contextual entry points currently claim
  evidence context without passing an accepted entity identifier. Coordinate
  with the active `work/cosmic-intelligence-realdata-maximum-1` lane.
- Protected frontend test ownership: the prior eight Invoice, Customer-history,
  and Financial Reports fixture failures are now repaired in protected
  authority. They remain recorded in history but are no longer active handoffs.
- Estimate operator UI: after the protected fixture repairs, all 554 assertions
  pass, but the full run reports one unhandled exception in
  `EstimatesRoute.tsx` when `estimate.data.current_revision` becomes undefined
  after “preserves staged services while searching for another line.” The
  Estimate workspace must either keep the selected revision coherent or render
  a truthful unavailable state; LIA does not patch Estimate lifecycle state.

## Sweep record

### Sweep 1 — actionable defects found

Covered Customers, Employees, Jobs, Scheduling, Dispatch, Price Book,
Estimates, Invoices, Payments, Timekeeping, Payroll, Accounting periods,
Economics, Beacon/Luminary navigation, text/voice intent, response modes,
permissions, missing evidence, route context, and period comparisons.

Result: eight bounded LIA-owned defects repaired. This sweep does not count
toward the required three consecutive clean sweeps.

### Sweep 2 — actionable defects found

Re-ran the connected Customer/Job/Employee lookup paths, explicit record
navigation, malformed contextual entry, response modes, authorization-aware
retrieval, source limitations, and newly protected Estimate workflow changes.

Result: four additional bounded LIA-owned defects repaired. Protected Estimate
changes require no LIA contract change: the accepted Estimate adapter and
canonical `/estimates` workspace remain compatible. This sweep does not count
toward the required three consecutive clean sweeps.

### Sweep 3 — actionable defect found

Exercised foreground voice capture, conversation mode, speech output,
interruption, cancellation, inactivity, mutation-intent refusal, and the shared
text/voice evidence path.

Result: one privacy/recovery lifecycle defect repaired. This sweep does not
count toward the required three consecutive clean sweeps.

### Clean sweep 1 — retrieval, authority, and evidence

Covered exact Customer/Job/Employee resolution, ambiguity and existence
hiding, Company/Branch isolation, Payroll guidance and protected-field
exclusion, temporal evidence, source-backed/native authority, incomplete data,
and adversarial safety. Focused result: 83 passed; no new actionable LIA-owned
defect.

### Clean sweep 2 — web, navigation, and voice lifecycle

Covered contextual entry, authorized navigation, topic/period continuation,
malformed links, loading/error states, push-to-talk, conversation mode,
interruption, cancel, inactivity, mutation intent refusal, and concise spoken
output. Focused result: 20 passed; no new actionable LIA-owned defect.

### Clean sweep 3 — conversational breadth and non-mutation

Covered natural-language routing, correction, ambiguity, referents, topic
switching, comparisons, response modes, owner question corpus, provider-neutral
retrieval, high-impact requests, and cross-domain evidence composition. Focused
result: 83 passed; no new actionable LIA-owned defect.

The remaining backlog is source-domain or human/provider gated. No owned P0,
P1, or P2 defect remains after these three consecutive sweeps.

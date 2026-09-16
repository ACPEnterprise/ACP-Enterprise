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
- Price Book: an exact Branch-safe service/current-price evidence projection is
  required; LIA must not reproduce catalog joins.
- Revenue Cycle: Invoice/Payment relationship, application, settlement, cash,
  and historical-as-of evidence require domain-owned projections.
- Timekeeping: Employee/period accepted interval and hours evidence requires a
  Timekeeping-owned projection; scheduled duration is never substituted.
- Luminary/Economics presentation: contextual entry points currently claim
  evidence context without passing an accepted entity identifier. Coordinate
  with the active `work/cosmic-intelligence-realdata-maximum-1` lane.

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

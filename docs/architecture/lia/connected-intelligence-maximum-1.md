# LIA connected-intelligence qualification and source handoff

Authority base: `origin/customer-management-v1` at
`5f7a45118885a38e5faa4fcfcf98dd395d3ea7ea`.

This increment changes only the deterministic, read-only LIA composition layer.
It adds no operational command, persistence, provider, or schema.

## Qualified connected surface

| Domain | Current LIA evidence | Connected behavior | Remaining source-owned gap |
| --- | --- | --- | --- |
| Customer | `CUSTOMER.LIA_CONTEXT.v1` | Exact authorized name resolution; bounded Locations, Jobs, Appointment, Estimate, Invoice, Payment, and Agreement states; entity navigation | Historical source-only records remain limited to what the Customer projection admits |
| Job | `JOB.LIA_CONTEXT.v1` | Exact Job-number resolution; bounded Customer, Location, Appointment, Dispatch, Estimate, Invoice, Payment, and worked-time states; entity navigation | Detailed related-record identities require a Job-owned drill-back projection |
| Scheduling | bounded Appointment state/date adapter | Today/tomorrow/week filtering and canonical Schedule navigation | A source-owned bounded result projection is required for named/ordered Appointment answers such as “open the first appointment” |
| Dispatch | bounded assignment state/window adapter | Period-aware assignment states and canonical Dispatch navigation | A source-owned result projection is required for technician/Appointment drill-back and historical lifecycle explanations |
| Workforce | `WORKFORCE.LIA_CONTEXT.v1` | Exact authorized Employee resolution, readiness, Mobile state, Payroll follow-up context | Detailed work history requires a Workforce-owned bounded history projection |
| Price Book | bounded service-item state adapter | Authorized state totals and canonical Price Book navigation | Exact service lookup and current-price evidence need a Branch-safe Price Book read projection; the existing catalog search is not an LIA evidence contract |
| Estimates | bounded Estimate state/created-date adapter | Period-aware state totals and canonical Estimates navigation | Natural Estimate identity and Customer/Job-related drill-back need a bounded Commercial projection |
| Invoices | bounded Invoice state/issue-date adapter | Period-aware state totals and canonical Invoice navigation | Historical as-of balance and natural Invoice identity need Revenue Cycle authority |
| Payments | bounded receipt state/capture-date adapter | Period-aware receipt states without treating receipt existence as settlement | Customer/Invoice application, settlement, and cash distinctions need a bounded Payments projection |
| Financial Reports | canonical report adapter | Exact period/basis requests use posted-ledger report authority; unavailable basis/period fails closed | Missing source/native reports remain an Accounting/QBO admission gap; LIA does not calculate replacements |
| Timekeeping | bounded accepted-revision work-date adapter | Authorized period totals by state and Workforce navigation | Per-Employee interval/hour summaries need a Timekeeping-owned projection; scheduled duration is never substituted |
| Payroll readiness | canonical Payroll operations/reporting adapters | Employee referent follow-ups and protected-value-free blocker guidance | Missing Payroll inputs remain owner/accountant/source gates reported by Payroll |
| Economics/Luminary | admitted result and briefing adapters | Period-bound measurements/interpretations with authority labels | No LIA recomputation; absent admitted result remains an Economics source gap |

## LIA-owned defects repaired

- Initial single-domain answers now bind a bounded continuation topic, so a
  follow-up such as “What about tomorrow?” stays in Scheduling without a UUID.
- An explicit topic switch clears the prior entity identifier before retrieval;
  Customer or Employee context cannot contaminate a later Scheduling query.
- Exact corrections re-resolve Customer, Job, and Employee subjects through the
  same Company/Branch-scoped resolvers. Ambiguous and missing matches continue to
  fail closed.
- Natural Price Book, Invoice, and Payment phrases route to bounded registered
  sources without creating a generic search path.
- Financial Reports navigation now targets `/financial-reports`; Timekeeping
  evidence navigates to the existing `/employees` operating surface rather than
  a nonexistent route.
- The deterministic 112-question owner corpus now reflects protected Customer,
  Job, and Payroll integration instead of stale pending-candidate gates.

## Safety invariants

Authorization is evaluated before retrieval. Client context supplies neither
Company nor Branch ownership. Topic changes discard incompatible entity IDs.
Corrections use exact authoritative resolvers, not fuzzy source identity.
Evidence digests, temporal context, source authority, and stale-context handling
remain intact. No mutation primitive, provider call, transcript persistence, or
new domain truth was introduced.

## ENTERPRISE.INTELLIGENCE and OM2 handoffs

The source-owned gaps above are independently actionable contracts. In
particular, Scheduling/Dispatch must return bounded authorized record references
for ordered/drill-back answers; Price Book must expose an exact Branch-safe
service/current-version projection; Revenue Cycle must expose Invoice/Payment
relationship and historical-as-of semantics; and Timekeeping must expose an
Employee/period summary. LIA must consume those projections after admission and
must not reproduce their joins or calculations.

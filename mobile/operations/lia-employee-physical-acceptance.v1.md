# ACP Employee LIA physical acceptance

This runbook is executable only after the employee-safe server contract is
deployed to the selected Preview environment. It uses no owner LIA endpoint and
does not provision or mutate an Employee.

## Preconditions

- Install the approved ACP Employee build pinned to Preview.
- Use the authorized test identity **Michael Brian** only after the owner confirms
  that the identity has `COMPANY_EMPLOYEE_OPERATIONS_OWN_LIA_READ`.
- Confirm the response from `/api/v1/lia/employee/ask` is available in Preview.
- Do not enter or record passwords, tokens, activation secrets, Payroll values, or
  protected Customer data in evidence.

## Acceptance sequence

1. Launch ACP Employee and confirm the environment is Preview.
2. Confirm the LIA entry is visible only when the effective permission allows it.
3. Ask: “What’s next on my schedule?” Confirm an employee-safe answer, current
   evidence/freshness, as-of information, and no company-wide schedule data.
4. Ask: “What jobs are mine this week?” Confirm only authorized assignments are
   returned; an empty result must be clearly distinguished from denied access.
5. Ask about an assigned Job. Confirm the answer is assignment-scoped and does
   not expose unrelated Customer history, financial data, or other Employees.
6. If the response includes canonical available action metadata, open the
   returned Employee destination and confirm the current permission-scoped
   screen. If metadata is absent, confirm Mobile remains guidance-only and does
   not guess a route from text.
7. Ask about own clock/time status. Confirm the answer reflects authoritative
   timekeeping evidence and does not calculate Payroll.
8. Ask for an unrelated Customer. Confirm the server returns a safe denied,
   hidden, or incomplete response without revealing the record identity.
9. Ask for owner Economics, Beacon recommendations, or Luminary findings.
   Confirm employee-safe denial; the client must never retry through `/api/v1/lia/ask`.
10. Expand supporting evidence. Confirm source, freshness, completeness, and
   limitations remain visible without exposing protected payloads.
11. Use Speak on an authorized answer. Confirm shared semantic speech content,
    calm local playback, Stop, replay, and no raw restricted fields.
12. Disable network and submit a question. Confirm a truthful offline/network
    error and no fabricated answer.
13. Restore network and retry. Confirm the answer is fetched from the server and
    conversation continuity is preserved where supported.
14. Background the app during playback. Confirm speech stops and no audio remains
    active behind the screen.
15. Sign out. Confirm protected LIA state and playback are cleared.

## Pass criteria

- Every answer is from the employee-safe route and current server authority.
- No owner endpoint fallback occurs.
- No owner Economics, Beacon, Luminary, Payroll administration, company-wide
  Customer/Scheduling, or foreign assignment data is disclosed.
- Partial, unavailable, stale, denied, and incomplete states are truthful.
- No Production request, Employee mutation, Customer communication, or Payroll
  operation occurs.

## Evidence to record

Record only build/version, route classification, safe correlation ID, response
classification, completeness, freshness, and pass/fail outcome. Never record
credentials, tokens, raw protected payloads, or screenshots containing them.

# LIA Conversation Quality Maximum 1

## Boundary

This increment adds deterministic interpretation before the existing governed LIA
planner. It recognizes response mode, corrections, explicit periods, bounded
referents, capability questions, and non-executing action intent. It neither owns
domain facts nor retains a durable transcript. Retrieval, Company/Branch authority,
evidence digests, staleness checks, and navigation remain governed by the existing
LIA contracts.

Action recognition is explanatory only. It returns the action type, risk class,
read-only refusal, and an authorized product destination. It never creates a
proposal or invokes a mutation.

An older topic cannot be restored from `Go back` unless it is supplied in the
currently authorized bounded context. This avoids inventing durable-memory policy.
Temporal phrases resolve to explicit local calendar dates. Where an adapter does
not accept a date range, LIA discloses that limitation rather than labeling an
all-time summary as a period result.

## Authority language

- `ACP_AUTHORITATIVE`: “ACP's native authorized records show…”
- `SOURCE_BACKED`: “Authorized source evidence shows…”
- `PARTIAL`: “ACP has only part of the authorized evidence…”
- `INSUFFICIENT_EVIDENCE`: LIA states what source or referent is missing.

Raw authority codes remain in the response contract, not the primary owner answer.

## Physical owner acceptance — 50 questions

Score each result as `USEFUL_PASS`, `SAFE_BUT_NOT_USEFUL`, or `FAIL`. A safe refusal
is useful only when it identifies the missing authority/referent or the correct
read-only destination.

1. How's business?
2. How are we doing?
3. What's going on today?
4. What should I be worried about?
5. What's broken?
6. What still needs me?
7. Give me the morning briefing.
8. What changed since yesterday?
9. Anything new since lunch?
10. What should I look at before I leave?
11. Show me Lianne Hernandez.
12. Is she payroll ready?
13. What is holding Payroll up?
14. Just tell me what matters.
15. Show me the evidence.
16. No, I meant Alex.
17. Is he mobile ready?
18. Back to Lianne — what needs the accountant?
19. Go back.
20. What can you do?
21. Can you run Payroll?
22. Approve Payroll.
23. Show me the Smith Customer.
24. What work have we done for them?
25. No, the other Smith.
26. The Clearwater one.
27. Show me that Customer's open Jobs.
28. Open the first one.
29. Was that Job paid?
30. Who worked it?
31. What is scheduled tomorrow?
32. Who has the Smith Job?
33. Where is Jason today?
34. What needs scheduling?
35. Move this Job to tomorrow.
36. Assign Jason.
37. Send the Estimate.
38. Why can't we invoice this Job?
39. What did we charge that Customer last time?
40. Raise drain cleaning five percent.
41. Do we make money on drain cleaning?
42. Why?
43. What costs are missing?
44. What does Luminary recommend?
45. What Beacon issues need attention?
46. Explain that alert.
47. Why can't I see May numbers?
48. What were sales in May 2026?
49. How much did we collect?
50. Is that QuickBooks source evidence or ACP-native?

## Expected gates

The interpreter and safety paths are locally deterministic. Usefulness of Customer,
Job, Payroll guidance, breadth, and voice questions still depends on Enterprise
integrating the separately frozen source/retrieval candidates and on authoritative
business evidence being present. No test fixture converts an absent upstream source
into business truth.

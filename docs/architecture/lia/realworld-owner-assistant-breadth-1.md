# LIA real-world owner assistant breadth 1

This increment keeps `LIA.READ_ONLY.v1` and the existing governed retrieval
registry. It changes no source authority and adds no mutation surface.

## Acceptance corpus

The deterministic corpus contains 112 questions across Customer, Job, Employee,
Scheduling, Dispatch, Payroll, Finance, Migration, Luminary, Economics, Beacon,
Price Book, Mobile, and launch readiness.

| Result | Count | Meaning |
| --- | ---: | --- |
| `USEFUL_PASS` | 94 | Current bounded evidence and the owner composer can produce a useful answer or truthful domain-specific explanation. |
| `SAFE_BUT_NOT_USEFUL` | 18 | The request fails safely but awaits a named prerequisite below. |
| `FAIL` | 0 | No accepted deterministic case is allowed to fail open or fabricate. |

The 18 gated cases are:

- 2 natural Customer/Job identifier entry cases awaiting qualified candidate
  `32a7986d6609433662b089b46df295c9306951ad`;
- 8 Payroll actionability cases awaiting frozen qualified candidate
  `a18efea7b5a0aa600b1bc17dbcdb616fab742e37`;
- 3 May/historical financial statement questions awaiting admitted statement
  authority (Accounting-period readiness is not a P&L);
- 4 Price Book decision-detail questions awaiting a bounded decision projection;
- 1 Apple-specific Mobile readiness question, which remains an external gate.

## Response behavior

The final deterministic composer now produces domain-specific conclusions for
contextual Customer/Job/Employee/Asset evidence, Scheduling and Dispatch,
Accounting readiness, Migration, Business Economics/Luminary, Beacon, Workforce,
and real-world launch readiness. It preserves adapter authority and digests,
keeps missing evidence explicit, and supplies navigation rather than execution.

Financial figures are never inferred from period readiness. Migration run evidence
is never described as operationally available history. Economics results are not
recalculated. Beacon signals are not cleared. Launch work is not called closed
merely because it was implemented.

## Integration order

Enterprise should independently integrate the frozen Payroll and Customer/Job
candidates, then reconcile this composer increment. If either candidate touches
the same service composition seam, retain its more specific subject/actionability
behavior and use this increment as the fallback for all other domains.

# LIA spoken presence v1

## Boundary

The authoritative LIA answer remains the visual and evidentiary record. Spoken
presentation is a deterministic rendering of that answer; it is not another
planner, model, evidence source, or authority.

Pipeline:

```text
authorized LIA retrieval and composition
  -> LiaResponse (answer, authority, response_mode, evidence, next action)
  -> unchanged visual response and evidence cards
  -> deterministic spoken presentation
  -> platform speech synthesis
```

The spoken renderer may change cadence and wording without changing facts. It
never reads or derives new claims from raw evidence payloads.

## Presentation rules

- Preserve names, business record references, monetary values, dates, times,
  counts, negation, uncertainty, and authority distinctions.
- Remove UI preambles, bullets, table separators, opaque UUIDs, and known
  internal readiness codes.
- Use contractions and connected sentences where meaning is unchanged.
- Lead with the answer and limit speech according to the server-selected
  `BRIEF`, `NORMAL`, `DETAILED`, or `EVIDENCE` mode.
- Add no more than one server-provided safe next action.
- Do not speak evidence details by default. `EVIDENCE` mode increases the
  sentence budget but still uses only the composed answer.
- State when evidence is source-backed if the visual answer does not already
  make that distinction.
- Never convert missing, partial, stale, or denied evidence into certainty.

## Delivery

Web speech synthesis prefers the default local English platform voice, then any
local English voice, before falling back to the browser default. Delivery uses
a calm `0.94` rate, neutral pitch, and full volume. This does not select a
branded voice or external provider.

## Representative transformations

Before:

> Customer status active. Jobs count 7. Balance 842 dollars.

Spoken:

> I found the customer; they're active. 7 jobs are on record. The outstanding
> balance is $842.

Before:

> Lianne is not payroll-ready. COMPENSATION_MISSING_CONFIGURATION.
> TIME_EVIDENCE_MISSING.

Spoken:

> Lianne isn't payroll-ready. Compensation setup is missing. Accepted time is
> missing.

Before:

> QuickBooks source evidence shows May income of $125,000 and June income of
> $130,000. The reports use the accrual basis.

Spoken retains both figures, the periods, the accrual basis, and the
source-backed qualification.

## Mobile handoff

The response envelope now carries `response_mode`. ACP Employee/iPhone should
consume this same field and apply the same presentation invariants before native
speech. Mobile must not create a separate answer, planner, or authority path.

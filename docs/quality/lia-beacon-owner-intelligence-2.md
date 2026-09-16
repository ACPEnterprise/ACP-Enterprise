# LIA.BEACON.OWNER.INTELLIGENCE.2

## Authority and recovered work

- Protected authority: `541fe77e690993996acf7f0f66139edd7cbf8578`.
- Recovered qualified successor: `92be0b1d74a3023d9abbffd4fc3abaf5e4792036`.
- The successor is one commit ahead of protected authority and makes the Beacon
  morning brief consume the already-authoritative append-only evaluation history.
- This branch preserves that work rather than recreating Beacon evaluation or
  attention authority.

## Bounded intelligence increment

Beacon owner briefings now distinguish a genuinely completed evaluation window
from a window with no persisted evaluation. New, changed, resolved, and expired
counts come only from persisted Beacon evaluation dispositions. The brief digest
binds the exact history records, their evidence digests, evaluation times, and
evidence-as-of times.

Period-aware LIA consumes the same Company/Branch-scoped history contract for
windows of at most 31 days. It returns:

- `AUTHORITATIVE_SIGNAL_HISTORY` when a completed evaluation exists, including an
  authoritative zero when no changes were recorded;
- `PERIOD_AUTHORITY_UNAVAILABLE` when no completed evaluation exists;
- an explicit unavailable state before retrieval when the requested history window
  exceeds the accepted bound.

The evidence reference binds Company, Branch, authorization version, period,
timezone, source contract, stable digest, disposition counts, and source
evidence-as-of lineage. Owner wording explains recorded outcomes without claiming
causality or granting remediation authority. Two-period comparisons display both
comparable disposition sets without inventing a trend or priority.

## Security and authority

`ANALYTICS_READ` remains mandatory before any history query. Retrieval supplies the
current authorization-resolved Company and active Branch to Beacon; client-supplied
tenant ownership is not accepted. LIA remains read-only and cannot acknowledge,
snooze, assign, resolve, or remediate a Beacon signal.

## Qualification

- Fresh PostgreSQL zero-to-head migration followed by current-authority upgrade:
  `q3s1t29j6w2x` (single head).
- Focused Ruff: passed.
- MyPy for `app/beacon` and `app/lia`: passed.
- Beacon and LIA tests: 320 passed; one pre-existing Starlette deprecation warning.
- Python compilation and `git diff --check`: passed.
- No frontend files or contracts changed; no frontend test run was required.
- No migration was added by this increment.

## Real-data boundary

Public Preview health was reachable at deployed release
`a109743968fc764fc1885ecf8fbd4abeb87846d7`, and authenticated LIA/Beacon routes
correctly returned `401` without a sanctioned owner session. Therefore no All County
business payload was read and no real-data result is claimed. After integration and
deployment, ENTERPRISE.INTELLIGENCE must rerun the bounded owner questions against
the All County tenant under a sanctioned owner identity:

1. “What changed in Beacon today?”
2. “What became urgent today?”
3. “What is still open from yesterday?”
4. “Compare Beacon in this week and last week.”
5. “Why does this active Beacon condition exist?”

The first four require persisted completed evaluation runs for the requested
Company/Branch periods. The fifth continues to use current Beacon intelligence and
supporting evidence. Absence of a run must remain unavailable, not zero.

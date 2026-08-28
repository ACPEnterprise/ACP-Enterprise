# Beacon operational signal prioritization

`BANK.BEA.004.v1` derives a read-only attention queue from signals already
admitted by Beacon evidence readiness and quality rules. It never admits a
signal, changes lifecycle state, or mutates a source domain.

Ordering is lexicographic and deterministic:

1. declared signal severity, highest first;
2. catalog definition priority band, highest first;
3. an explicitly registered operational urgency fact, greatest elapsed duration
   first;
4. stable signal UUID, ascending.

Only overdue committed appointments (`oldest_overdue_hours`) and stalled
intermediate Jobs (`oldest_pause_hours`) currently have approved urgency
semantics. These are versioned fact-ordering policies, not invented SLAs or
thresholds. Definitions without an approved urgency policy receive no time
ordering.

The queue excludes inadmissible, expired, snoozed, and otherwise suppressed
signals. Its canonical digest binds the ranking version, authorized
Company/Branch scope, ordered signal identities, declared priority facts,
quality digests, and approved urgency values. Ranking never changes the signal
UUID. Legacy invoice exposure remains in the backward-compatible legacy Beacon
projection and is not admitted to the operational queue.

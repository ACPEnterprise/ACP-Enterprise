# Authoritative queue discovery and recovery

The Development Factory now discovers queue-bearing refs by inspecting every
published `refs/heads/handoff/*` ref. It does not depend on branch-name keywords.
This corrects the OM1 polling defect where the fallback filter omitted both
`queue` and `overnight`, leaving the new authoritative queue invisible while
the poller repeatedly checked obsolete named refs.

`GitQueueSource` fetches the handoff namespace into a coordination-only local
ref namespace, finds the commit that last changed the queue file, validates the
existing queue contract, and selects the sole ancestry-maximal queue revision.
An unrelated or non-descendant supersession fails closed.

`QueueDiscoverySupervisor` adds only a durable discovery and recovery adapter
around the existing coordination contract. It does not create a claim, lease,
approval, merge, or deployment path. Its checkpoint provides:

- bounded network retries and ref/candidate/assignment limits;
- queue digest and supersession fencing;
- machine-specific manual-reservation projection;
- machine-bound begin, recovery, reconciliation, completion, and shutdown;
- completed-evidence and dependency recognition;
- duplicate execution prevention;
- crash/restart reconciliation; and
- atomic, integrity-checked, mode-`0600` state with safe shutdown.

Manual reservations remain excluded from the automated claim-envelope path.
Laptop Master remains the assignment and integration authority.

Every supervisor lifecycle command requires `--machine`. The checkpoint binds
each assignment to the machine in Laptop Master's manual reservation. A second
machine cannot begin, reconcile, or complete that assignment, and restart or
shutdown recovery changes only running assignments owned by the calling
machine. Locally sealed completion is retained across discovery, clears only
its declared dependents, and cannot cause the completed assignment to be
offered again.

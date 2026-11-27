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

## Bounded continuation

When Laptop Master is preparing a successor queue, the supervisor can poll the
same authoritative handoff namespace without reverting to fixed ref names:

```bash
PYTHONPATH=backend python3 -m development_factory \
  --repo-root . coordination supervisor-continue \
  --machine OM1 \
  --state "$PRIVATE_STATE_PATH" \
  --max-polls 6 \
  --base-poll-seconds 5 \
  --max-poll-seconds 30
```

Polling and exponential backoff are bounded (`64` polls and `60` seconds per
delay are hard maxima). The result is exactly one of `WORK_AVAILABLE`,
`QUEUE_EXHAUSTED_BOUNDED`, or `SAFE_SHUTDOWN`. The mode-`0600` checkpoint
records idle start, idle poll count, last work time, and per-machine continuation
status. A replenished descendant queue resets idle state. Restart uses the same
checkpoint and cannot re-offer completed work.

Safe shutdown moves only the calling machine's running assignments to
`reconciliation_required`, records the machine, and exits without approval,
merge, deployment, or protected execution. A later successful discovery clears
that machine's shutdown marker but does not bypass reconciliation.

## Persistent unattended supervisor

The bounded continuation command is a foreground discovery operation; it does
not persist after its terminal session and does not execute assignments. A
persistent engineering session must use `supervisor-run` with an exact,
committed execution plan:

```bash
PYTHONPATH=backend python3 -m development_factory \
  --repo-root . coordination supervisor-run \
  --machine OM1 \
  --execution-identity OM1-B \
  --state .development-factory/om1b/coordination.json \
  --runtime-state .development-factory/om1b/runtime.json \
  --plan docs/engineering/evidence/om1b-unattended-execution-plan-20261127.json \
  --poll-seconds 60 \
  --max-assignments 8 \
  --max-runtime-seconds 21600
```

This process reuses authoritative queue discovery and the existing durable
checkpoint. It adds no claim or lease path. Every discovery, begin, restart,
reconciliation, completion, and shutdown is bound to both the physical machine
and the six-lane execution identity. An OM1-B process cannot execute an OM1-A
reservation on the same host.

The execution plan contains no command line or shell fragment. It binds each
assignment to the SHA-256 digest of its exact queue assignment and manual
reservation, and selects one of the built-in read-only qualification profiles.
Changed scope, an unknown assignment, a different authority ref, unsupported
profile, missing dependency, low disk, excessive supervisor memory, a second
active process, or a secret-bearing plan fails closed.

The mode-`0600` runtime journal records process starts, assignment transitions,
resource observations, evidence digests, idle polls, and bounded exits. A
restart retains local completions so they are never reoffered and can unlock an
authorized successor. If a process stops while an assignment is running, the
assignment becomes `reconciliation_required`; it is never replayed without
durable completion evidence. Automatic commit, push, merge, deployment,
protected execution, and Worker Control claims remain disabled.

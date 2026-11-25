# Durable Development Factory Coordination

The Development Factory uses Worker Control and controlled execution as the
authoritative cross-machine assignment and lease service. The local durable
coordination journal supplements that authority; it does not issue assignments,
leases, approvals, commits, merges, or deployments.

## Authority and fencing

Every local claim is bound to an immutable assignment, execution, worker,
Worker Control lease ID/version/expiration, and queue digest. The journal uses
an owner-only shared custody root and an exclusive POSIX lock so two local
processes cannot acquire the same execution, assignment, file boundary, or
declared resource. Lease renewal must advance exactly one version. A process
holding an older version is fenced from checkpoints and completion.

The custody root may be shared by isolated worktrees on a machine. A
cross-machine filesystem must provide correct POSIX locking semantics. Worker
Control remains the cross-machine source of truth regardless of storage layout.

## Checkpoints and recovery

Checkpoints are canonical JSON records chained by SHA-256. The complete state
also has a digest. Every read verifies the full chain before returning data.
Writes use an owner-only temporary file, `fsync`, atomic replacement, and a
directory `fsync`.

An incomplete journal discovered after restart becomes
`reconciliation_required`; it is never replayed automatically. Releasing the
local fence requires the exact reviewed state digest and the current authority
fence. Expired authority may be released after review but cannot perform new
work.

## Bounded execution

Transient network retries are limited to a configured attempt count and delay.
Only explicitly declared exception types are retryable. Each failed attempt is
checkpointed with secret redaction. File boundaries, resources, checkpoints,
evidence bytes, active claims, and all worker termination-policy values have
hard ceilings independent of worker-supplied values.

Permanent regression coverage exercises atomic races, overlapping file and
resource claims, stale lease writers, checkpoint tampering, crash/restart,
bounded network retries, secret redaction, and resource ceilings.

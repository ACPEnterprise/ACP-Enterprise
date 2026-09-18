# Speech training-run ledger v1

Training state is digest-chained evidence rather than a mutable terminal label.
Every event binds the exact run, dataset, configuration digest, prior/next
state, time, reason, predecessor digest, and its own digest.

Allowed execution is `PLANNED -> RUNNING -> SUCCEEDED|FAILED|CANCELED`.
Pre-execution refusal is explicit. Terminal states cannot reopen, times cannot
move backward, successful runs require artifact digests, and failed runs require
bounded failure evidence. This contract does not start training or claim that a
dataset, compute runtime, checkpoint, or model exists.

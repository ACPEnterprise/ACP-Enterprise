# Speech model promotion ledger v1

Model lifecycle is append-only evidence, not a mutable `accepted` switch. Every
transition binds model identity/version, prior and next state, reason, actor,
time, prior-event digest, and its own canonical digest.

The permitted path is `DEVELOPMENT -> CANDIDATE -> QUALIFIED -> ACCEPTED`, with
terminal `SUPERSEDED` or `REVOKED` transitions where allowed. States cannot be
skipped, rewritten, reopened, or applied across model versions. Qualification
and acceptance require a qualified, digest-valid model artifact.

Current-model resolution validates every ledger and returns the single terminal
`ACCEPTED` model. Multiple accepted candidates fail as an authority fork rather
than selecting by timestamp. No persistence, model promotion, training,
inference, or deployment is performed by this in-memory governance contract.

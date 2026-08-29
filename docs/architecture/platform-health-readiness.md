# Platform health and readiness

ACP exposes liveness separately from readiness. `/health/live` proves only that
the process can answer HTTP. `/health` and `/health/ready` return a typed,
hierarchical projection whose component states are `HEALTHY`, `DEGRADED`,
`NOT_READY`, `BLOCKED`, or `UNKNOWN`.

Database authority and exact single-head schema agreement are hard readiness
requirements. Redis is classified as session/coordination infrastructure and is
required by default, preserving the existing authentication rate-limit safety
boundary. Environments may explicitly classify Redis as degradable; no in-memory
authority substitute is created. A Redis outage never changes durable database
truth.

The public projection contains only component classification, safe reason,
observation time, and non-sensitive facts such as schema revision. Connection
strings, credentials, provider configuration, and business payloads are never
returned. Optional workers, providers, and storage must be added as explicit
probes before they can be reported healthy; absence of a probe is not promoted
to readiness.

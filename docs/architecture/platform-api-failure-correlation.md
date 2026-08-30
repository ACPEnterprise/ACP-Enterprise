# API failure and correlation contract

ACP binds every HTTP request to a safe UUID correlation identity. A client UUID
may be preserved; malformed or payload-shaped values are rejected as correlation
authority and replaced. The same identity is returned in `X-Request-ID` and is
available to domain, Business Event, background-work, provider, and
reconciliation adapters without embedding protected data.

Shared mutation failures expose a machine-readable recovery disposition:
`RETRY_SAFE`, `RETRY_AFTER_REFRESH`, `USER_CORRECTION_REQUIRED`,
`OWNER_ADMIN_ACTION_REQUIRED`, `RECONCILIATION_REQUIRED`,
`TEMPORARILY_UNAVAILABLE`, or `TERMINAL_FAILURE`. Domain-specific codes remain
authoritative; this vocabulary describes client recovery and does not erase the
domain reason.

Idempotency conflicts require correction, in-progress identical work is safe to
retry, and missing authoritative outcomes require reconciliation. Responses use
safe classifications and correlation identities only. Database constraint names,
provider errors, stack traces, paths, credentials, and protected payloads are not
part of the contract. Possession of either correlation or idempotency identity
never substitutes for current authorization.

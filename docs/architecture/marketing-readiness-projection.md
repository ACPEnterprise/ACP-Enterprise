# Marketing readiness projection

`GET /api/v1/marketing/readiness` publishes the Company-scoped, read-only `marketing-readiness.v1` contract. It derives safe aggregate state from the platform provider connection binding and canonical Marketing account bindings, sync runs, observations, coverage manifests, and reconciliation findings.

The endpoint requires `COMPANY_MARKETING_READ`. Branch mappings and evidence are limited to the caller's authorized Branches. It never returns tokens, credentials, developer tokens, secret references, or provider payloads.

Owner states are deterministic:

- `CONFIGURATION_REQUIRED`: runtime configuration still blocks authorization.
- `READY_TO_AUTHORIZE`: the owner may start Google authorization.
- `AUTHORIZED_ACCOUNT_SELECTION_REQUIRED`: authorization exists, but no account/Branch binding has been confirmed.
- `CONNECTED_NOT_INGESTING`: an account is bound, but ingestion is disabled or has no successful sync.
- `INGESTING`: ingestion is enabled and a successful sync exists.
- `DEGRADED`: the provider failed or unresolved reconciliation evidence remains.

Spend evidence is `UNAVAILABLE` when no observation contains cost, `PARTIAL` when only some performance observations contain cost, `STALE` when the latest provider evidence is more than 72 hours old, and `AVAILABLE` otherwise. This is evidence readiness only: it does not calculate ROI, revenue, gross profit, or economic contribution.

Beacon consumes this projection as an active readiness adapter. Luminary and LIA may consume the same protected contract. None may infer provider state or expose provider credentials.

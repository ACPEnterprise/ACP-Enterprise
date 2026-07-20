# API Standards

ACP Enterprise APIs are stable product contracts. They must be consistent across the web application, field clients, integrations, automation, and future external consumers.

## REST conventions

- Use HTTPS outside local development.
- Use nouns for resources and plural paths: `/api/v1/customers`, `/api/v1/jobs/{job_id}`.
- Use `GET` to read, `POST` to create or invoke a non-idempotent domain command, `PATCH` for partial updates, and `DELETE` only where deletion is a valid domain operation.
- Use nested paths only when the child is meaningfully scoped to the parent, and keep nesting shallow.
- Represent workflow transitions explicitly when ordinary resource updates would obscure rules, for example `POST /api/v1/jobs/{job_id}/complete`.
- Return `201 Created` with a `Location` header for creation, `202 Accepted` for asynchronous acceptance, and `204 No Content` only when no response body is useful.
- Support idempotency keys on creation, payment, external callback, and retry-prone command endpoints.
- Use ISO 8601/RFC 3339 timestamps with offsets. Store and transmit instants in UTC; include the applicable business timezone when returning business-period calculations.
- Represent monetary values as integer minor units plus ISO currency code in new contracts. Do not use binary floating point.

## Versioning

- Public application APIs are path-versioned under `/api/v1`.
- Additive, backward-compatible fields do not require a new version.
- Do not rename, remove, reinterpret, or narrow a published field within a version.
- Deprecations must be documented, observable, communicated to consumers, and retained through an agreed migration window.
- A breaking change requires a new API version or a coordinated pre-release migration when no published consumer exists.
- Event schema versioning is independent from REST API versioning.

## Request and response validation

- Validate syntax, type, range, format, allowed transitions, and cross-field business rules.
- Reject unknown fields on write contracts unless forward-compatible metadata is explicitly intended.
- Normalize inputs only when the transformation is deterministic and documented.
- Server-derived fields such as tenant, actor, totals, permissions, and audit timestamps are never trusted from clients.
- Use separate schemas for creation, update, response, and internal persistence where their semantics differ.
- Publish representative request, success, validation, authorization, and conflict examples in OpenAPI.

## Error responses

All non-success responses use a consistent envelope:

```json
{
  "error": {
    "code": "appointment_time_unavailable",
    "message": "The selected appointment window is no longer available.",
    "details": [
      {
        "field": "start_at",
        "reason": "conflict"
      }
    ],
    "request_id": "01J..."
  }
}
```

- `code` is stable and machine-readable.
- `message` is safe and useful to a human.
- `details` is optional structured context, especially for field validation.
- `request_id` links the response to logs and traces.

Use status codes consistently:

- `400` malformed request outside ordinary field validation
- `401` missing or invalid authentication
- `403` authenticated but not authorized
- `404` absent resource or a resource intentionally concealed by tenant policy
- `409` state, uniqueness, idempotency, or workflow conflict
- `422` syntactically valid request that fails input validation
- `429` rate limit exceeded
- `500` unexpected internal failure
- `502` or `503` required dependency unavailable

## Pagination

- Collection endpoints are always bounded.
- Prefer cursor pagination for changing or high-volume collections. Use an opaque cursor with deterministic ordering and a unique tie-breaker.
- Offset pagination is acceptable for small administrative datasets and early internal APIs when its scale limit is documented.
- Default and maximum page sizes must be defined; the platform default is 50 and maximum is 200 unless a resource documents stricter limits.
- Return pagination metadata in a consistent shape:

```json
{
  "items": [],
  "page": {
    "next_cursor": null,
    "has_more": false
  }
}
```

Do not calculate total counts by default when doing so is expensive.

## Filtering, sorting, and search

- Use query parameters: `?status=scheduled&branch_id=...&sort=-start_at`.
- Document allowed filters, sort fields, operators, defaults, and combinations.
- Ignore no unknown filter or sort parameter; reject it with validation details.
- Use repeated parameters or a documented comma-separated format consistently for multi-value filters.
- Date-range filters define inclusive/exclusive boundaries and timezone semantics.
- Search endpoints must state which fields are searched and whether results are eventually consistent.
- Enforce tenant and authorization filters before user-supplied filters.

## Authentication

- All non-public endpoints require an authenticated principal.
- Use standards-based short-lived credentials issued by the chosen identity provider. Browser credential storage must minimize exposure to script access.
- Service and integration identities are distinct from human users and have scoped credentials.
- Credential validation includes issuer, audience, signature, expiry, and revocation/session policy as applicable.
- Authentication failures reveal no sensitive account state.

## Authorization

- Authorization is enforced server-side for every operation and resource.
- Evaluate tenant, branch, role, permission, resource ownership, and relevant workflow state.
- Derive tenant and actor context from the authenticated session; never accept them as authoritative request fields.
- Collection queries must apply the same policy as individual resource reads.
- Sensitive exports, impersonation, role changes, refunds, and financial adjustments require explicit permissions and audit events.
- The UI may hide unavailable actions for usability, but UI checks never replace API enforcement.

## Contract quality

- OpenAPI generation must pass CI and be reviewed when contracts change.
- API tests cover success, validation, authentication, authorization, tenant isolation, conflict, and idempotency behavior.
- Avoid returning unbounded JSON payloads or internal fields “in case they are useful.”
- Measure endpoint latency and error rate by route template, not raw resource identifier.

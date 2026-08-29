# Sensitive-data Logging Controls

## Boundary

`BANK.PLAT.007` defines the ordinary operational-output boundary shared by all
ACP Companies. It covers standard application logs, structured extras,
exception summaries, audit details, Business Event metadata, provider/worker
summaries, diagnostics, and test output. It does not create a second logging or
audit system, grant data access, persist sanitized copies, or replace domain
authorization and tenant isolation.

## Classification

The canonical catalog in `app.platform.security.safe_output` distinguishes:

- **secret** — credentials, passwords and hashes, tokens, keys, connection
  strings, payment tokens, and bank/routing values;
- **sensitive value** — personal contact data, free text, compensation, payroll,
  and attachment content whose raw value is unnecessary for operations;
- **protected source payload** — raw provider, Migration, acquisition, and
  financial-source material;
- **safe reference** — opaque Company, Branch, actor, resource, correlation,
  event, and idempotency identities.

Classification is field-contract driven. Pattern sanitation is only a last-line
defense for private-key blocks, bearer credentials, and credential-bearing URLs;
it is not the primary credential-control mechanism. New domains extend the
registered field sets and canary tests rather than adding local redaction rules.

## Safe-output contract

`sanitize()` recursively handles mappings, collections, dataclasses, Pydantic
models, UUIDs, and unknown objects. Registered protected values are replaced
with classification markers. Unknown objects expose only a type and digest.
Canonical SHA-256 digests retain useful correlation without retaining the raw
value. Identical input produces identical sanitized output and catalog
fingerprints.

The installed standard-library logging filter sanitizes messages, positional or
structured arguments, and custom record fields. Exception tracebacks and raw
exception messages are removed from ordinary handlers and replaced with a safe
code, classification, exception type, correlation identity when supplied, and
digest of exception-type lineage. It never retains exception messages in the
safe view.

## Audit and Business Events

Audit evidence retains actor, subject, action, Company/Branch, timestamp,
decision identity, correlation, and safe digest/provenance. Audit details reject
all registered secret, sensitive, and protected-payload fields rather than
silently deleting accountability.

Business Events reject secret and protected-source fields before persistence.
Personal or commercial facts remain allowed where an accepted domain contract
intentionally makes them authoritative business facts; logging those complete
event payloads is still prohibited. Events are not a generic diagnostic channel.

## Compatibility

- Identity onboarding already uses generic operator errors and protected secret
  envelopes. The Platform catalog recognizes invitation, verification, reset,
  login-email, password, and password-hash fields without modifying onboarding.
- Compensation, hourly rate, salary, payroll result, and deductions are
  protected using synthetic qualification only.
- QBO transport's existing URL filter and Migration's protected-source contracts
  remain authoritative and compatible. Platform protection is an outer generic
  boundary, not a competing source loader or evidence model.
- Worker/provider implementations can sanitize structured summaries or create a
  `SafeExceptionView`; no worker scheduling or provider semantics changed.
- No frontend telemetry product exists in the accepted architecture. This
  milestone adds no browser telemetry and sends no protected form values.

## Testing and operations

Synthetic canaries cover credentials, tokens, connection strings, email,
compensation, payment/bank values, raw source payloads, nested structures,
exception chains, audit, and Business Events. Tests assert canaries do not appear
in captured output while safe status, count, identity, and digest fields remain.
Real customer, employee, provider, Migration, QBO, HCP, payment, or bank data is
never required.

Operational code should log stable codes and sanitized structured fields. It
must not pass request bodies, ORM objects, provider responses, financial source
rows, credentials, or free-form exceptions directly to ordinary telemetry.

# Coding Standards

These standards apply to production code in ACP Enterprise. They favor explicit business ownership, predictable structure, and maintainability across many teams. Automated formatting, linting, type checking, and tests should enforce rules wherever practical.

## General standards

- Make the smallest coherent change that satisfies documented behavior.
- Prefer readable, typed code over clever abstractions.
- Keep business rules in the module that owns them and independent of HTTP or UI frameworks where practical.
- Never commit secrets, customer data, production exports, or credentials.
- Do not introduce a dependency without explaining its purpose, maintenance status, security posture, and operational cost.
- Remove dead code and superseded paths in the same change after migration is complete.
- Preserve backward compatibility or document and coordinate the migration.

## Backend architecture

The backend is a FastAPI modular monolith. Organize code first by business module, then by responsibility:

```text
backend/app/<module>/
├── router.py          # HTTP transport and dependency wiring
├── schemas.py         # request/response contracts
├── service.py         # application use cases and transaction boundary
├── models.py          # module-owned SQLAlchemy models
├── repository.py      # persistence queries when complexity warrants it
├── events.py          # event contracts and publication
└── errors.py          # module-specific domain/application errors
```

Small modules may omit files they do not need. Do not create empty layers merely to match the diagram.

- Routers parse transport input, invoke one application use case, and translate results. They do not contain business calculations or SQL.
- Services coordinate authorization, domain rules, repositories, transactions, and event creation.
- Repositories encapsulate reusable or nontrivial persistence behavior and never commit transactions independently.
- SQLAlchemy models are persistence definitions, not API schemas.
- Pydantic request and response schemas are explicit; never expose ORM models directly as an accidental public contract.
- Cross-module access occurs through a public application interface or event, never by writing another module's tables.
- Use asynchronous I/O consistently on request paths. Do not call blocking clients from the event loop.

## Frontend architecture

Organize the React application by product feature as it grows:

```text
frontend/src/
├── app/               # application shell, routing, providers
├── features/<module>/ # screens, components, hooks, module API adapters
├── shared/            # reusable UI and framework-neutral utilities
├── api/               # generated client and transport configuration
└── types/             # genuinely cross-feature types
```

- Route-level components compose screens; they do not implement backend business rules.
- React Query is the source for server-state caching and invalidation. Do not mirror server collections into global client state.
- Keep feature-specific components, hooks, and types with their feature.
- Use shared components only after reuse is real and their contract is stable.
- Generate or mechanically derive TypeScript API types from the OpenAPI contract when the API stabilizes.
- Provide explicit loading, empty, error, stale, and unauthorized states.
- Meet WCAG 2.1 AA expectations for keyboard use, semantics, focus, contrast, and form errors.
- Lazy-load substantial routes and monitor bundle size and runtime performance.

## Naming conventions

### Python and database

- Python modules, functions, and variables: `snake_case`
- Python classes and Pydantic/SQLAlchemy types: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Database objects and columns: `snake_case`

### TypeScript and React

- Variables and functions: `camelCase`
- Components, types, and interfaces: `PascalCase`
- React component files: `PascalCase.tsx`
- Hooks: `useSomething`
- Feature utility files: descriptive `camelCase.ts`

### Domain language

- Use one business term consistently across UI, API, code, database, and documentation.
- Event types use lowercase dotted past tense: `appointment.booked`.
- Avoid ambiguous names such as `data`, `manager`, `helper`, or `status` when a precise domain name exists.
- Include units in names when ambiguity is possible, such as `duration_minutes` or `amount_cents`.

## Folder organization and boundaries

- Every business-owned file belongs to a named module.
- `core` or `shared` contains stable technical primitives, not miscellaneous code.
- A module may depend on Foundation and Platform plus dependencies documented in the [module map](../architecture/module-map.md).
- New cross-module dependencies require review for ownership and cycles.
- Import through a module's declared interface when one exists; private implementation details are not contracts.

## Dependency injection

- Use FastAPI dependencies at the transport boundary for request-scoped concerns such as sessions, authenticated principals, tenant context, and service construction.
- Pass explicit dependencies into services and domain functions. Avoid hidden global clients and mutable singletons.
- The application owns connection pools and long-lived clients and closes them during shutdown.
- Tests replace dependencies at clear boundaries rather than patching deep implementation details.
- A service that begins a transaction passes the same session or unit of work through participating repositories.

## Logging and observability

- Emit structured logs suitable for machine parsing.
- Include timestamp, severity, environment, service version, request or job ID, correlation ID, tenant ID, actor ID when appropriate, event name, and safe contextual identifiers.
- Never log passwords, tokens, payment credentials, message contents, or unnecessary customer data.
- Log once at the boundary that owns handling of an exception; avoid repeated stack traces across layers.
- Use metrics for rates and distributions, traces for cross-boundary latency, and events/audit records for business history. Logs are not an audit database.
- Health, readiness, queue lag, external dependency failures, and critical workflow error rates must be observable.

## Error handling

- Raise typed domain or application errors for expected failure conditions.
- Translate errors to the standard API envelope at the HTTP boundary.
- Do not expose stack traces, SQL, credentials, or internal implementation details to clients.
- Unexpected errors return a stable generic response and retain a correlation ID for support.
- Roll back failed transactions and do not emit an event for a state change that did not commit.
- Define timeout, retry, and idempotency behavior for every external call. Retry only transient failures and use bounded backoff.
- Frontend error states must tell the user what failed, whether work was saved, and what recovery action is safe.

## Documentation expectations

- Public APIs, event schemas, migrations, configuration, operational procedures, and non-obvious business rules require documentation.
- Docstrings explain intent or constraints that types and names cannot express; they do not restate code.
- Consequential architecture changes require an ADR.
- Product workflow changes update the relevant module specification and acceptance criteria.
- Documentation changes ship in the same pull request as implementation.
- Comments explain why a constraint exists and link to an issue or document when context would otherwise be lost.

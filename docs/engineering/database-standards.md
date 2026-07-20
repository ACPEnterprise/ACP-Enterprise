# Database Standards

PostgreSQL is the authoritative transactional database for ACP Enterprise. Database design must protect tenant isolation, referential integrity, auditability, and predictable performance.

## PostgreSQL

- Use supported PostgreSQL releases and managed production storage where practical.
- Use SQLAlchemy for application persistence and Alembic for schema evolution.
- Store timestamps as timezone-aware values and normalize instants to UTC.
- Use `jsonb` only for genuinely variable metadata or versioned event payloads, not to avoid modeling queryable business fields.
- Represent money with integer minor units and an ISO 4217 currency code. Existing decimal contracts should migrate deliberately; never use floating point.
- Use database constraints for invariants that PostgreSQL can reliably enforce.
- Application services own transactions; repositories do not commit independently.

## Alembic migrations

- Every schema change has a reviewed Alembic migration committed with the code that requires it.
- Migrations must have deterministic upgrade behavior and an accurate downgrade where safe. If reversal would lose data or is operationally unsafe, document the forward-recovery procedure instead of providing a misleading downgrade.
- Test upgrades from the current production revision on representative data.
- Separate long-running data backfills from blocking schema changes. Use expand/migrate/contract for changes that cannot be deployed atomically.
- Avoid table rewrites and long exclusive locks during business hours.
- Application startup must not create or mutate schemas automatically.
- Production migration execution is an explicit release step with logs, ownership, backup verification, and failure handling.
- Alembic configuration obtains the database URL from environment configuration; credentials do not belong in committed migration files.

## Identifiers and UUIDs

- Use UUID primary keys for business entities and externally visible records.
- Generate identifiers in the application before persistence when they are needed for events or related writes.
- Prefer time-ordered UUIDs for new high-volume tables when framework and PostgreSQL support are standardized; otherwise use UUIDv4 consistently.
- Never encode tenant, type, timestamp, or sensitive business meaning in an identifier.
- API consumers treat identifiers as opaque strings.

## Naming conventions

- Tables use plural `snake_case` names: `service_locations`.
- Columns, indexes, constraints, and sequences use `snake_case`.
- Primary keys are `id`; foreign keys are `<entity>_id`.
- Timestamp columns end in `_at`; dates end in `_date`; boolean columns use affirmative names such as `is_active`.
- Constraint and index names identify table and columns, for example `uq_customers_company_id_external_ref` and `ix_jobs_company_id_status_scheduled_at`.
- Use consistent domain terms from the [module map](../architecture/module-map.md) and product specifications.

## Tenant ownership

- Tenant-owned root and high-volume tables include non-null `company_id`; branch-owned records include non-null `branch_id` where the concept applies.
- Foreign keys and unique constraints include tenant scope when needed to prevent cross-tenant association.
- Application queries always apply tenant policy. PostgreSQL row-level security should provide defense in depth before multi-company production use.
- Global lookup tables must be explicitly designated and contain no tenant-private data.
- Database roles follow least privilege; migration, application, analytics, and support access use separate roles.

## Indexes

- Create indexes for proven query, join, uniqueness, foreign-key, and tenant-filter patterns.
- Tenant-owned query indexes normally begin with `company_id` and then equality filters, ordering/range columns, and a stable tie-breaker.
- Add indexes for foreign keys used in joins or deletes; PostgreSQL does not create them automatically.
- Use partial, covering, expression, or GIN indexes only with a documented query and measured benefit.
- Review write amplification and unused indexes. More indexes are not automatically better.
- Validate important queries with realistic volumes and `EXPLAIN (ANALYZE, BUFFERS)` outside production-sensitive paths.

## Foreign keys and constraints

- Use foreign keys for persistent relationships unless a documented cross-service boundary makes them impossible.
- Choose `ON DELETE` behavior deliberately. Default to restriction; cascade only when the child has no independent lifecycle and deletion is safe.
- Use `NOT NULL`, unique, check, and exclusion constraints to protect data integrity.
- State transitions and multi-row business rules remain in the owning domain service, with locking or concurrency control where required.
- Do not create polymorphic foreign keys that the database cannot validate for core business relationships.

## Soft deletes and retention

- Soft deletion is a business decision, not a universal default.
- Use `deleted_at` and `deleted_by_user_id` when records must disappear from normal workflows but remain recoverable or auditable.
- All normal reads and uniqueness rules must handle soft-deleted records explicitly.
- Financial records, audit records, and business events are not silently deleted. Use reversals, corrections, or retention procedures appropriate to legal and operational requirements.
- Define retention and purge processes for customer data, attachments, logs, exports, and integration payloads. A soft-delete flag is not a retention program.

## Audit fields and concurrency

Transactional business tables normally include:

- `id`
- `company_id` and, where applicable, `branch_id`
- `created_at`, `created_by_user_id`
- `updated_at`, `updated_by_user_id`
- `deleted_at`, `deleted_by_user_id` when soft deletion is required
- A version field or equivalent concurrency token where lost updates are possible

Audit timestamps are generated consistently by trusted application or database infrastructure. Audit fields complement business events; they do not replace an append-only record of meaningful actions.

## Operational safety

- Production has automated encrypted backups and tested point-in-time recovery.
- Restore tests occur on a defined schedule and record recovery time and recovery point evidence.
- Sensitive fields are classified, access-controlled, minimized, and excluded from ordinary logs and analytics copies.
- Connection pools, statement timeouts, lock timeouts, slow queries, storage growth, replication, and migration state are monitored.

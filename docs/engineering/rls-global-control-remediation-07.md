# Global/control privilege remediation scope

This is an isolated qualification assignment only. It does not authorize live
role, grant, RLS, schema, or data changes.

The protected snapshot showed 19 public tables with `acp_app` INSERT/UPDATE/
DELETE and `relrowsecurity=false`. `alembic_version` is excluded from the
application privilege remediation because it is migration metadata. The 18
application tables are:

| Table | Initial classification | Required review |
|---|---|---|
| `access_agreement_documents` | global agreement catalogue | retain global read; restrict writes to agreement publication authority |
| `authentication_security_events` | global security audit | append-only service path; no ordinary tenant DML |
| `authentication_sessions` | identity/session control | identity-service ownership; no ordinary tenant DML |
| `branch_scheduling_exceptions` | branch scheduling control | verify branch/company ownership before scoped writes |
| `branch_scheduling_weekly_intervals` | branch scheduling control | verify branch/company ownership before scoped writes |
| `companies` | tenant root | identity-bound administrative writes only |
| `economics_evidence_acceptance_contracts` | global evidence contract | retain global read; restricted publication/update authority |
| `email_verification_tokens` | credential/token control | identity-service ownership; no ordinary tenant DML |
| `engineering_command_ecid_sequences` | global engineering sequence | sequence/service ownership; no tenant policy guessed |
| `identity_onboarding_invitations` | identity/onboarding control | identity-service ownership; tenant binding validated separately |
| `password_reset_tokens` | credential/token control | identity-service ownership; no ordinary tenant DML |
| `permissions` | global permission catalogue | retain global read; restricted synchronization authority |
| `platform_authority_assignments` | platform authority control | platform authority ownership; not tenant-scoped by default |
| `protected_invitation_delivery_envelopes` | protected delivery control | delivery-service ownership; secret-safe access only |
| `refresh_tokens` | credential/token control | identity-service ownership; no ordinary tenant DML |
| `user_credentials` | credential control | identity-service ownership; no ordinary tenant DML |
| `users` | global identity root | identity-bound administration; memberships provide tenant scope |
| `worker_identities` | platform worker identity | Worker Control ownership; no business-tenant policy guessed |

The remaining `alembic_version` row is migration metadata and must be owned by
the migration role, not treated as an application table. The next step is an
isolated grant/ownership rehearsal using `acp_app`, `acp_migrate`, and the
appropriate identity/platform service roles, followed by negative tests. No
live Beta role or policy change is implied.

# Employee Administration Onboarding Program 1

- Base authority: `902193d5cd258d58dab9621b687bbdc0b20ca0b7`
- Branch: `work/employee-administration-onboarding-program-1`
- Data: synthetic/non-Production only
- Schema: no new revision; current head `h6f7d04c2a8b`

The program reconciles Employee Workforce Administration with authoritative Asset
integration and adds owner-friendly permission metadata and onboarding-time effective
authority review. Permissions are grouped by business area, labeled read/mutation,
own-data, and high-impact, searchable, and filterable.

Canonical roles remain the baseline. An administrator holding both onboarding and
permission-management authority may add an explicit Employee permission profile in
the same onboarding transaction. The profile is a deterministic Company role bound
to the onboarding request, is additive only, is included in the request digest, and
advances authorization version. Exact replay converges through the existing onboarding
request identity. Subtractive deny semantics are deliberately not invented: select a
narrower baseline role, then add explicitly reviewed permissions.

The existing protected invitation lifecycle remains authoritative for creation,
reissue, revocation, activation, and non-Production owner claims. External delivery
remains provider-gated; an outbox/envelope is never represented as delivered email.

Enterprise acceptance must run the identity/onboarding PostgreSQL suite, Company
Administration authorization tests, mutation coverage, frontend tests/build, static
checks, and synthetic persona/mobile contracts. Preview deployment and physical-iPhone
execution remain separately owned.

# Employee and Workforce Administration Program 1

## Authority and composition

Employee Administration composes, but does not collapse, the authoritative User,
Company Membership, Employee, Branch grant, role, permission, onboarding, and
Workforce evidence identities. Payroll compensation, tax, banking, credentials,
activation material, and another Employee's own-data are excluded.

The Add Employee workflow uses the existing protected onboarding transaction. It
performs authoritative login-identity collision checks, creates or reuses the
appropriate User only under that contract, creates one Company Membership and one
Employee linkage, grants an explicit Branch and baseline canonical role, and records
provider-neutral invitation readiness. Creating an outbox intent is not represented
as delivered email.

## Administrative lifecycle

- The directory remains Company/authorized-Branch scoped and exposes operational
  identity, readiness, capabilities, languages, and availability only.
- The detail composition adds Membership state, authorization version, explicit
  Branch grants, role bundles, effective permission explanations, onboarding state,
  and deterministic Mobile readiness blockers.
- Membership, Branch, and role changes use the existing Company Administration
  APIs. Those commands advance authorization state and preserve final-administrator
  safety according to authoritative security behavior.
- Role permissions are additive through the existing role catalog. This program
  does not invent per-Employee deny or subtraction semantics.
- Deactivation keeps User credentials, Company Membership, Employee operational
  identity, and historical Payroll/operational evidence distinct. No historical
  evidence is deleted.

## Workforce evidence

The administration commands reuse the existing Company-scoped Workforce profile,
capability, certification, language, and availability tables. Stable evidence
identity makes exact PUT replay converge. Contradictory reuse fails with the safe
`RESOURCE_STATE_CONFLICT` / `RETRY_AFTER_REFRESH` contract. Catalog entries must be
active and belong to the same Company. Availability additionally requires an
authorized Branch.

Readiness is deterministic from recorded evidence. Real proficiency classifications,
credential requirements, working windows, emergency availability, persistent named
crew policy, and training requirements remain unconfigured.

## Acceptance and external gates

Synthetic acceptance covers canonical Technician, Dispatcher, SERVICE_CSR,
OFFICE_MANAGER, COMPANY_ADMINISTRATOR, and OWN_DATA_ROLE personas. Own-data authority
is always resolved server-side from the authenticated Membership to Employee link.
Physical-device execution remains with the Mobile lane. Transactional email remains
`PROVIDER_NOT_CONFIGURED`; no invitation is described as sent without provider
delivery evidence.

### Lianne readiness packet

No Employee is created by this packet. A later explicitly authorized live step must
provide and approve all of:

1. authoritative login email;
2. Company and Branch grant(s);
3. canonical baseline role;
4. any additional role-permission grants after owner-friendly review;
5. invitation delivery authorization after a provider is configured.

The live step then follows identity review, Membership/Employee linkage, Branch
grant, baseline role, effective-permission review, invitation preparation, delivery
evidence, activation, and Mobile readiness verification. No value is guessed.

### Bulk current-Employee readiness

Bulk onboarding is a candidate-review process, not blind HCP permission inheritance.
Each candidate requires normalized identity review, ambiguity disposition, Company
Membership and Employee-link inspection, Branch and role review, permission review,
invitation readiness, and an exception state. No bulk creation or delivery is
authorized by this program.

## Integration boundary

There is no Alembic revision. Integration must run the focused PostgreSQL Workforce
administration tests, Company Administration and onboarding suites, authorization and
own-data tests, mutation-coverage fingerprint test, frontend tests/build, and standard
static/security checks. Preview deployment and real Employee acceptance remain
outside this branch.

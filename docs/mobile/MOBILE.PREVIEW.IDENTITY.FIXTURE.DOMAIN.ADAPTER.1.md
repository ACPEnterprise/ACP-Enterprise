# Mobile Preview identity fixture domain adapter

Authority base: `5d8ef3c9a372cc47511fd583281cc702a9817fff`.

The server-side `PreviewIdentityFixtureService` binds the sanctioned
`acp-employee-beta-v1` identity fixture to existing application services. It does
not expose an HTTP route, CLI apply command, direct-SQL path, or live Preview
transport.

Provisioning delegates to the authoritative Identity Onboarding transaction. The
fixture key is the onboarding request key, so exact replay converges and conflicting
replay is rejected by existing digest authority. That transaction owns User,
Membership, Branch access, Employee linkage, roles/permissions, and the protected
invitation. The adapter additionally requires runtime environment `preview`, an
explicit authorization boolean, the exact fixture key, an authorized Branch through
the caller context, and a non-routable `.invalid` login that is not an All County
identity.

Identity reset first verifies the Company/Branch-scoped onboarding record and exact
fixture request key. A pending invitation is revoked through Identity Onboarding.
Active sessions are then revoked through Authentication authority, and Membership
access is revoked through Company Administration. An activated invitation is already
consumed, so it is not falsely reclassified as pending; session and Membership
revocation still remove access. Employee and audit history are retained rather than
deleted.

## Remaining operational fixture gap

The broader field-day fixture cannot yet be safely bound end-to-end. Customer and Job
offer idempotent creation, Scheduling accepts a deterministic idempotency UUID, and
Dispatch assignment accepts an idempotency key. Service Location creation is not
idempotent, and the owning domains do not provide a complete fixture-scoped teardown
contract for Location, Job, Appointment, Dispatch, Timekeeping, and Field evidence.
Archive/cancel operations retain truthful business history but cannot prove that an
arbitrary record belongs exclusively to this fixture.

Therefore operational apply/reset remains fail-closed. A successor requires
fixture-key ownership evidence and owning-domain reset methods; it must not compensate
with direct SQL or broad deletion. This is an engineering gap, not an owner policy
decision. No Preview mutation, communication delivery, Apple action, or Production
operation occurred here.

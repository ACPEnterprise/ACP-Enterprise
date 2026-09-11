# OM1 Phone launch status

Updated: 2026-09-10 America/New_York

## Authority

- Protected base: `42a4f68087d76247269bd4c8388f556dd62a8b5c`
- Mission: `origin/work/launch-20260911-mission`
- Mission commit: `0c08f1e3634f38a7fb82970932dea5de7a4cf24f`
- Mission file SHA-256: `03b74b5f065694b487268bdee531d8d50620f2816f30c91d8b665f9d5b3e9dfc`

## Lianne delivery coordination

OM1 Phone performed a read-only Preview reconciliation using the mission-pinned
invitation and outbox identities. No recipient address or activation material is
recorded here.

The existing onboarding request is `invited`; its invitation is `pending`,
unconsumed, and valid until `2026-09-12T00:32:52.574990+00:00`. The existing
User, invited Membership, active Employee, Company binding, MAIN Branch binding,
owner-selected role, and exact recorded recipient are preserved. The protected
envelope remains recoverable.

The outbox row is terminal `failed` after a definitive Postmark HTTP 422 / code
412 rejection. It has no provider reference and no surviving submitted marker,
so there is no ambiguous provider submission to reconcile before one approved
retry. Preview's identity delivery worker is running.

The owner reports Postmark approved. Enterprise owns the one live Preview retry
and must coordinate the consumer. Current protected authority does not expose an
audited operation that reopens this terminal failed row: the existing recovery
routine applies only to legacy `ambiguous` rows with the exact old safe error code.
Do not directly edit the outbox row, recreate the employee, reissue while the
invitation remains valid, or run a competing consumer. Enterprise should either:

1. use an existing audited operational retry interface not visible in this source
   tree; or
2. integrate and deploy the smallest authorized retry operation that locks this
   exact row, verifies terminal definitive rejection/no provider reference/current
   invitation validity, appends recovery evidence, and schedules the original
   outbox identity once.

After Enterprise executes, record separately: outbox claim, provider submission,
Postmark MessageID/accepted response, webhook delivery if available, human receipt,
activation, and login. Provider acceptance is not human receipt or activation.

## OM1 Phone next work

- Continue isolated fixture qualification for activation expiry/replay/revocation,
  password establishment/login, role refresh, and Mobile required permissions.
- After human activation evidence, verify active Membership and assign/verify
  `ACP_EMPLOYEE_MOBILE` through the sanctioned Administration path while preserving
  the owner's selected role and MAIN Branch.
- Hand Laptop1 Phone the Preview client contract without credentials or activation
  secrets. Physical-device ownership remains Laptop1 Phone.

No Production, Apple signing/TestFlight, Customer communication, shared password,
or real employee mutation was performed by OM1 Phone in this checkpoint.

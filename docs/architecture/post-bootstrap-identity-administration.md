# Post-Bootstrap Identity Administration

## Ownership model

ACP keeps five authorities distinct:

- `User` is the global authenticated identity.
- `UserCredential` owns password lifecycle and never exposes a plaintext password.
- `Membership` grants one User access to one Company and explicit Branches.
- `Employee` is optional workforce identity linked explicitly through Membership.
- Role and Permission assignments determine server-resolved authority.

Bootstrap remains a one-time initialization ceremony. It is not an onboarding or
repair tool.

## Invitation lifecycle

An administrator holding `COMPANY_IDENTITY_ONBOARDING_MANAGE` submits a
Company-scoped request with an idempotency key, active Branch, and roles. The
service either creates an invited User or reuses an eligible verified global User;
it never duplicates email identity. New-user invitations are expiring, single-use,
revocable, and reissuable. Only a token hash and safe digest are durable identity
evidence. The delivery secret is encrypted in the protected envelope until the
notification provider claims it, then destroyed after delivery or activation.

The public `/invitation#token=...` route keeps the claim secret out of HTTP request
paths and submits it only to the activation endpoint. Activation hashes the invited
user's chosen password, activates User and Membership atomically, consumes the
invitation, and invalidates replay. Administrators never choose or retrieve the
credential.

## Authorization and tenant safety

Branch, Membership, roles, optional Employee, audit, notification, and Business
Event evidence are bound to the administrator's Company. A role may be assigned
only when every effective permission on that role is also held by the inviter;
this prevents onboarding from becoming a privilege-escalation boundary. Existing
User identity never implies access to another Company.

Identity-only office and acceptance users do not receive Employee records.
Employee linkage is explicit and uses the permanent Company employee-number
authority. Linking does not expose compensation, Payroll, tax, or bank data.

## Operator experience

Administration lists safe masked identities and invitation states, creates an
invitation with explicit Branch and role selection, and supports revoke/reissue.
It never renders credentials, tokens, password hashes, session material, or
protected Employee fields.

## Preview acceptance

Preview may use the protected invitation delivery provider and local protected
secret storage for synthetic acceptance identities. Production provisioning,
provider selection, real Employee onboarding, and credential export are outside
this contract. Mobile uses the same activated User/Credential/Membership and,
where applicable, explicit Employee link; it does not receive a parallel identity.

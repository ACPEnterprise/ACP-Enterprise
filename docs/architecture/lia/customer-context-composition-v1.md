# Customer / Job LIA context composition v1

`CUSTOMER.LIA_CONTEXT.v1` is the Customer-domain-owned minimum-necessary
projection for contextual Ask LIA requests. A route supplies only an opaque
`domain` plus entity UUID. The server resolves Company ownership, current
authorization version, active/authorized Branches, permissions, and related
records before returning any evidence. A missing, foreign, revoked, or
unauthorized identity produces no projection and does not reveal existence.

## Included evidence

- Customer UUID, display label, lifecycle state, and Company identity.
- Authorized Branch identities that bounded the query.
- Up to 10 active Service Location UUIDs and safe nicknames, only when linked
  to Jobs visible in the authorized Branch scope.
- Up to 10 recent visible Job UUIDs, Job numbers, states, and Branch IDs. A
  contextual Job is retained in the bounded result.
- Permission-gated grouped state counts for Estimates, Invoices, and Service
  Agreements.
- Current authorization version, explicit permission limitations, observation
  time, contract version, and a deterministic evidence digest.

The projection executes a fixed number of bounded grouped queries; it does not
load relationship collections or fan out once per related record.

## Explicit exclusions

The contract never includes contact names, phone numbers, email addresses,
postal addresses, gate/access information, raw Customer or Job notes, service
descriptions, attachments, payment instruments, Payroll data, credentials,
secrets, or underlying protected evidence payloads. Source text remains
untrusted data and cannot alter LIA policy, source selection, permissions, or
tool authority.

## Authority and product behavior

Customer context requires Customer read authority plus at least one permitted
Branch-bearing related source. Job context requires both Customer and Job read
authority. Each optional source is queried only when its own permission is
present. Company and Branch predicates are applied in the database query before
materialization.

Customer and Job detail surfaces expose a responsive Ask LIA entry only when
the necessary coarse permissions are present. `/lia` displays that server
authorization remains authoritative and submits only the opaque context. The
context grants no mutation authority, does not configure an AI provider, and
does not enable autonomous or Production action.

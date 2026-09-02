# LIA operational intelligence product program 3

`LIA.CONTEXT.v1` remains the governed request boundary. Program 3 composes current source-owned contracts without giving LIA ORM or mutation authority.

## Capability decision

- Customer, Job, Invoice, Economics, Luminary, Beacon, Migration, Payroll metadata, Purchasing, Inventory, Scheduling, Estimates, and Payments remain authoritative through their accepted bounded adapters.
- `ASSET.LIA_CONTEXT.v1` adds exact, Branch-scoped Asset/Fleet/Equipment context. It excludes VIN, serial, plate, and provider identity evidence and never adjudicates warranty coverage or invents maintenance policy.
- `WORKFORCE.LIA_CONTEXT.v1` adds exact, Branch-scoped operational readiness. Compensation, Payroll, tax, banking, and credential references are excluded. Permission and onboarding explanation require their separate Administration permissions.
- Communications exposes only bounded delivery-state evidence and intent digests. LIA cannot send or resend.
- Context entry points carry only an opaque entity UUID. Company and Branch ownership are resolved again on the server.

## Product and safety semantics

Answers use direct operational language, then evidence and material limitations. Asset, Workforce, and Communications questions route only to explicitly permitted adapters. LIA does not infer urgency, warranty eligibility, employee quality, causality, payment settlement, Accounting recognition, or Economics results.

All source text is untrusted data. Foreign Company, foreign Branch, unknown UUID, revoked permission, and inactive Membership remain fail-closed through request-time AuthorizationContext and source query predicates. No provider was configured or called. No source-domain mutation path was introduced.

## Remaining gates

- Conversation transcript retention is `POLICY_REQUIRED`; current LIA requests remain ephemeral except safe metadata audit.
- External AI is `PROVIDER_REQUIRED`; deterministic ACP operation remains available.
- Provider admission requires owner approval, privacy/data-processing review, credential isolation, bounded context, output validation, failure fallback, evaluation, cost controls, and no direct mutation.
- Service Location relationship composition, broad Customer communication history, and source-specific Accounting cash/AP projections remain `SOURCE_REQUIRED` where no accepted bounded contract exists.

Preview and Production are outside this program.

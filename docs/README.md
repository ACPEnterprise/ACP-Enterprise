# ACP Enterprise Documentation

This directory is the authoritative documentation set for ACP Enterprise. It records why the platform exists, how it is structured, how engineers are expected to build it, and what must be true before it is released.

ACP Enterprise version 1.0 has one mission: replace Housecall Pro for All County Plumbing & Leak. QuickBooks replacement and multi-company SaaS capabilities are later phases and must not expand version 1.0 scope unless the roadmap and applicable architecture decisions are deliberately revised.

## Documentation map

### Architecture

[`architecture/`](architecture/) contains durable, system-wide direction:

- [`vision.md`](architecture/vision.md) defines the mission, business outcomes, and long-term position.
- [`principles.md`](architecture/principles.md) defines the rules used to make technical decisions.
- [`module-map.md`](architecture/module-map.md) defines module responsibilities and dependencies.
- [`roadmap.md`](architecture/roadmap.md) describes the intended evolution of the platform.
- [`architecture/adr/`](architecture/adr/) contains Architecture Decision Records (ADRs). ADRs capture consequential decisions, alternatives, and tradeoffs. Accepted ADRs are not rewritten to hide history; superseding decisions receive a new ADR.

### Engineering

[`engineering/`](engineering/) contains standards that apply to implementation and delivery:

- Coding and repository structure
- API and database contracts
- Testing expectations
- The organization-wide Definition of Done

These documents are normative. A deliberate exception must be explained in the pull request and, when the exception affects platform architecture, recorded in an ADR.

### Product

[`product/`](product/) contains release scope, operational readiness, and module-level product specifications:

- [`release-plan.md`](product/release-plan.md) defines the version 1.0 launch sequence.
- [`launch-checklist.md`](product/launch-checklist.md) is the production-readiness gate.
- `product/modules/` is the home for specifications for CRM, dispatch, jobs, estimates, payments, and other product modules. Each specification should describe users, workflows, business rules, permissions, data, events, acceptance criteria, and out-of-scope behavior.

### Daily records

[`daily/`](daily/) contains concise development-day records. These records communicate progress, decisions, evidence, risks, and the next handoff; they do not replace issues, ADRs, or permanent module documentation.

## Maintenance rules

1. Update documentation in the same pull request as the behavior it describes.
2. Link to authoritative documents instead of duplicating their content.
3. Use explicit dates, versions, owners, and measurable acceptance criteria where relevant.
4. Describe the current system truth. Label future designs and proposals clearly.
5. Keep documents concise enough to remain maintainable, but complete enough to guide an engineer without oral context.
6. Review foundational documents at each release boundary and whenever product scope or architecture changes materially.

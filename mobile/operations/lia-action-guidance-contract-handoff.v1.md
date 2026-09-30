# LIA actionable guidance contract handoff

## Current state

The current `NavigationSuggestion` contract is text-only:

- `label`
- `internal_path`

Mobile must not infer a route, required permission, entity scope, or action
availability from that text. It must not expose owner destinations to an Employee.

## Smallest server-owned delta

Extend the canonical suggestion with optional authoritative metadata:

```text
label: string
destination: enum/string owned by the product route registry
required_permission: string | null
availability: AVAILABLE | HIDDEN | UNAVAILABLE
reason: string | null
entity_id: UUID | null
context: object | null
```

The server remains responsible for selecting suggestions, checking permission,
and determining availability. Mobile only renders or follows suggestions that
are explicitly available and match its allowlisted Employee destinations.

## Employee Mobile allowlist

The first Mobile destination set is intentionally narrow:

- My Day
- My Schedule
- My Jobs
- My Time Clock
- assignment-scoped Job Workspace

Payroll administration, Accounting, Customer reconciliation, Branch setup,
Marketing connections, Beacon owner views, Luminary owner views, and other
office destinations must never be navigated to from Employee LIA.

## Acceptance requirement

Until this metadata is present and the employee-safe route is deployed to
Preview, Mobile remains guidance-only: it displays `safe_next_action`,
completeness, evidence, limitations, and server-provided text, but does not
guess or execute a destination.

Laptop1-E must integrate and deploy this contract before enabling physical action
acceptance. No owner mutation is implied by a suggestion.

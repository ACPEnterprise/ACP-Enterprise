# Workforce readiness explanation 1 — Enterprise handoff

## Boundary

- Starting protected SHA: `15287f82f3c5a40a97baf2da4505beb24a7b58c3`.
- Presentation-only interpretation of existing authoritative blocker codes.
- No readiness algorithm, role, permission, Employee, assignment, or schema change.

## Owner behavior

Employee detail, Mobile-readiness warnings, and the real-roster activation console
now explain each blocker using three explicit fields:

- what evidence or authority is missing;
- who must act (`OWNER`, `EMPLOYEE`, `APPLE / EXTERNAL`, or `SYSTEM`);
- what becomes possible after the action.

Known identity, Membership, Branch, operating-role, Workforce-profile,
technician-capability, Mobile-role, password, and availability blockers have
specific language. Unknown future blocker codes fail safely: the UI says evidence
is incomplete and directs the operator to refresh and review instead of guessing.

The password explanation keeps establishment with the Employee. Capability and
Branch explanations require human confirmation and explicitly reject inference
from prior Jobs. Existing enum values remain available to the client contract but
are no longer the primary operator copy.

## Qualification

- Focused frontend tests: `8 passed`.
- TypeScript production build: passed.
- ESLint: passed with zero warnings.
- Diff and secret checks: passed.

No Preview or Production state was changed.

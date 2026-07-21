# Definition of Done

A workstream is done only when its approved outcome is complete and supported by
reviewable evidence. “Implemented” is not the same as done.

## Required gates

- **Architecture Approved:** ownership, boundaries, dependencies, transactions,
  data, events, and extension points match the reviewed design.
- **Validation Complete:** every applicable check in the
  [Validation Standard](validation-standard.md) has a recorded result.
- **Tests Passing:** focused tests and the required regression suite pass without
  unexplained failures, warnings, or skips.
- **Lint Passing:** applicable formatting and lint checks pass.
- **Type Checking Passing:** Python and TypeScript checks pass for affected scope.
- **Documentation Updated:** architecture, contracts, operations, and limitations
  reflect current behavior.
- **Security Reviewed:** authentication, authorization, tenant isolation, input,
  secrets, failure behavior, auditability, and sensitive output are reviewed.
- **Review Completed:** the complete diff and commit boundary have received
  technical review and unresolved findings are addressed.
- **No TODO Placeholders:** production behavior is not deferred through TODOs,
  fake integrations, or misleading UI.
- **No Dead Code:** obsolete branches, unused abstractions, and abandoned paths
  introduced or superseded by the work are absent.

The work must also satisfy its acceptance criteria and preserve unrelated work.
Commit and deployment require separate explicit approval under
[Branching and Release](branching-and-release.md).

An exception must identify the unmet gate, rationale, risk, compensating control,
owner, and resolution plan. Security, tenant isolation, data integrity, and
recoverability are not waived for schedule convenience.

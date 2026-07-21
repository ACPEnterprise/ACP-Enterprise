# Engineering Playbook

ACP Enterprise work follows one reviewable delivery flow:

```text
Business Workflow
↓
Domain Architecture Brief (DAB)
↓
Architecture Review
↓
Implementation
↓
Validation
↓
Technical Review
↓
User Approval
↓
Commit
↓
Deployment
```

## Workflow

1. **Business Workflow:** describe the user or operational outcome, rules,
   failure cases, and exclusions.
2. **Domain Architecture Brief (DAB):** translate the workflow into a concise,
   reviewable domain contract covering scope, objects, ownership, APIs, events,
   security, dependencies, risks, acceptance criteria, and extension points. Use
   the [DAB Standard](domain-architecture-brief-standard.md); implementation does
   not begin until the brief is approved.
3. **Architecture Review:** resolve material decisions before implementation.
4. **Implementation:** make the smallest coherent change using existing module,
   service, repository, design-system, and event boundaries.
5. **Validation:** run the checks selected by the
   [Validation Standard](validation-standard.md) and record exact results.
6. **Technical Review:** inspect the complete diff, architecture, security,
   concurrency, compatibility, tests, documentation, and repository hygiene.
7. **User Approval:** obtain explicit approval for the reviewed implementation
   and its commit boundary.
8. **Commit:** stage only approved files or hunks and create the approved atomic
   commit. Committing does not authorize pushing or deployment.
9. **Deployment:** follow a separately reviewed runbook and authorization. Verify
   the deployed revision, migrations, health, security, and critical workflows.

Stop when a required decision, permission, dependency, or validation result is
missing. Do not conceal an invalid intermediate state to satisfy process. Define
the work itself with the [Workstream Standard](workstream-standard.md).

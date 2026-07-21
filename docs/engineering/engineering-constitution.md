# Engineering Constitution

This constitution defines the durable principles used to resolve engineering
tradeoffs in ACP Enterprise. More detailed practices are linked from the
[ACES index](README.md).

## Principles

1. **Architecture Before Implementation.** Inspect the current system, define
   ownership and boundaries, and review consequential design choices before
   changing behavior.
2. **Business-Driven Design.** Model real operational workflows and invariants.
   Framework convenience does not determine the domain.
3. **Security First.** Authentication, authorization, tenant isolation, secret
   handling, auditability, and safe failure are design inputs, not final checks.
4. **Single Ownership.** Every rule, transaction, record, and contract has one
   accountable module or service. Other modules use its published boundary.
5. **Repository-Owned Persistence.** Repositories own queries, locking, ordering,
   and persistence mechanics. Services own transactions and business decisions;
   routers remain transport adapters.
6. **Testability.** Boundaries are explicit, dependencies are replaceable at
   supported seams, and important behavior is provable with deterministic tests.
7. **Modularity.** Keep platform, domain, presentation, and infrastructure
   responsibilities separate. Add abstractions only when they clarify ownership.
8. **Documentation.** Architecture, contracts, operational procedures, and
   non-obvious constraints change with the implementation they describe.
9. **Long-Term Maintainability.** Prefer clear, typed, conventional solutions over
   shortcuts, duplicated logic, speculative flexibility, or hidden coupling.
10. **Continuous Improvement.** Treat defects, review findings, and operational
    evidence as inputs for focused improvement without rewriting stable systems
    without demonstrated need.

## Applying the constitution

When principles compete, protect correctness, security, data integrity, and
recoverability first. Record consequential tradeoffs through the
[Architecture Decision Process](architecture-decision-process.md). Exceptions to
the [Definition of Done](definition-of-done.md) require explicit review; schedule
pressure alone is not justification.

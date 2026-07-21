# Architecture Decision Process

Architecture decisions record durable choices that future engineers need in order
to change ACP Enterprise safely. They complement implementation documentation;
they do not replace it.

## When a decision is required

Create or update an Architecture Decision Record (ADR) when a change materially
affects:

- domain or module ownership;
- security or tenant boundaries;
- persistence, migration, or transaction strategy;
- public API or event contracts;
- cross-module dependencies;
- platform-wide frontend, backend, or operational conventions;
- a difficult-to-reverse technology or deployment choice.

Routine implementation within an approved pattern does not need an ADR.

## Process

1. State the context, problem, constraints, and decision owner.
2. Describe viable alternatives and meaningful tradeoffs.
3. Select the decision and explain why it best satisfies ACP principles.
4. Record consequences, risks, compatibility, migration, and validation needs.
5. Obtain architecture review before dependent implementation.
6. Store the numbered ADR under `docs/architecture/adr/` and link it from affected
   architecture or engineering documents.

ADRs are append-only historical records. A later decision supersedes an earlier
one rather than rewriting the earlier context. Minor factual corrections remain
visible in normal Git history. Use the
[Engineering Constitution](engineering-constitution.md) to evaluate tradeoffs.

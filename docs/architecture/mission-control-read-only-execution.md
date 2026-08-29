# Mission Control read-only execution

`PHONE.FACTORY.READONLY.1` defines an `inspect_validate_only` controlled
execution profile. One authenticated owner Start creates the normal execution
lineage and permits automatic offer creation, but the immutable offer carries
`repository_mutation_allowed=false` and exactly the `inspect` and `validate`
operations. The provider validates an isolated checkout and must return
`repository_mutated=false`; it never invokes implementation, commit,
reconciliation, publication, deployment, Production, HCP, QBO, or payment
operations.

The three non-production qualification packets are:

- `PHONE.FACTORY.PROOF.OM1` — Repository Integrity Verification.
- `PHONE.FACTORY.PROOF.OM2` — Backend Validation Verification.
- `PHONE.FACTORY.PROOF.LAPTOP1` — Frontend/Architecture Validation Verification.

Each packet remains owner-Start gated, is bound to one qualified physical
capacity identity, and requires exact current authoritative/provider-ready
repository evidence. Logical terminal lanes do not create capacity.

The fresh `PHONE.FACTORY.1P` qualification packets are
`PHONE.FACTORY.PROOF2.1`, `PHONE.FACTORY.PROOF2.2`, and
`PHONE.FACTORY.PROOF2.3`. They retain the same inspect/validate-only contract,
freeze the deployed authoritative head at reconciliation and command admission,
and create no command, execution, offer, or lease until the owner presses Start.

The repaired offer-admission qualification set supersedes those actionable
definitions with `PHONE.FACTORY.PROOF3.1`, `PHONE.FACTORY.PROOF3.2`, and
`PHONE.FACTORY.PROOF3.3`. Their permanent OM1/OM2/Laptop1 affinities constrain
control acknowledgement and readiness refresh without granting repository
mutation authority. The prior PROOF2 execution evidence remains historical.

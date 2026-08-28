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

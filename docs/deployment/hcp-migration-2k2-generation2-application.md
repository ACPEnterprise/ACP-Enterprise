# HCP.MIGRATION.2K2 generation-2 application contract

HCP.MIGRATION.2K2 extends the existing `HcpMigration2Application` public boundary. It does not introduce a second runner. The application now accepts a `HcpMigration2SupersedingRepairAuthority`, validates the original plan and generation-1 failure lineage, and composes the K1 sequence plan, correction service, retained checkpoint, generation-2 Operational child, conformance admission, and existing Financial/completion envelope.

The generation-2 authority binds the master, original plan, generation-1 repair and failed child, superseding plan, sequence and checkpoint digests, repair generation, source package and builder, sanctioned actor, and Company/Branch. Any mismatch fails with a safe evidence code.

Execution checkpoints are durable and replayable:

1. persist or verify the canonical Appointment sequence plan;
2. atomically apply or verify per-Job sequence corrections and qualify generation-2 lineage;
3. reuse source-bound retained Jobs and Appointments and submit only remaining Appointment commands;
4. persist eligible Operational Estimates and require `EXECUTION_COMPLETED` plus `PLAN_CONFORMING`;
5. use the accepted Financial repair and atomic HOLD/outcome completion lifecycle.

An interrupted retry reuses the same sequence-plan and repair-generation identities. Operational runs resume by their existing run identity; source identities from that run are accepted checkpoints, progress is updated rather than duplicated, and exact exception outcomes are reused. Completed-master replay verifies generation-1 and generation-2 lineage, corrections, checkpoints, child admission, and final reconciliation without reapplying corrections or creating generation 3.

The additive `c6e8a0b2d435` migration records repair generation/ancestry, failed-child and sequence-plan binding, and retained/remaining identity digests. It preserves the existing Job/visit uniqueness constraint and does not rewrite prior repair evidence.

Only safe identifiers, counts, digests, and classifications may leave the application boundary. Protected SOURCE.4 rows and customer, Appointment, or financial payloads are not included in results or errors.

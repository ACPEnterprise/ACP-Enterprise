# HCP.MIGRATION.2L Financial evidence supersession

HCP.MIGRATION.2L preserves the native ACP Invoice invariant: a native Invoice requires at least one authoritative line item. A SOURCE.4 Invoice with no acquired line items is classified as `invoice_line_items_absent_source_evidence_only`; it is retained as a safe, hashed, master-bound plan outcome and never receives a fabricated line item or native Invoice identity.

The deterministic `hcp-migration-2l-financial-supersession/v1` plan binds the original Financial repair and nonconforming child, retained native Invoice and Payment source identities, evidence-only Invoice and Payment relationship dispositions, adjusted reconciliation counts, and immutable source evidence digests. Its execution path is composed only by `HcpMigration2Application` through `HcpMigration2FinancialSupersedingAuthority`.

For the sealed SOURCE.4 package, 663 native Invoices and 684 Payment assertions are retained. The 117 line-item-empty Invoice artifacts become evidence-only exceptions. No accepted Payment assertion references those 117 identities, so this package requires no additional Payment relationship row. The contract nevertheless classifies a Payment referencing an evidence-only Invoice as `source_invoice_evidence_only`, preserving the source relationship without a fabricated native Invoice foreign key.

Execution qualifies a generation-2 Financial repair linked to the completed nonconforming Financial child, runs an empty retained-identity checkpoint child, requires `PLAN_CONFORMING`, and only then atomically persists HOLDs, plan outcomes, and completion evidence. Completed replay verifies the successor repair/admission and evidence-only outcomes without duplicating native financial rows.

This milestone is qualification only. It does not execute the successor Financial repair or complete the retained rehearsal master.

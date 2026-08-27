# ECO.QBO.EVIDENCE.1 — Source-reported economics evidence bridge

This dependency-ready milestone connects the sealed QBO source package contract to
future Business Economics ingestion without starting blocked BE.9, adopting the
external Phase 8 engine, or claiming real profitability facts.

Each assertion retains the source manifest, immutable envelope and raw digests,
native type/ID, relationships, QBO-reported fields, and explicit authority:
`quickbooks_online_source_reported`. Its acceptance state is always
`unreconciled_not_enterprise_accepted` until later Accounting/Finance workflows
provide control reconciliation and disposition.

Invoices, credits, payments, purchases, bills, accounts and journals are classified
only as evidence assertions. No amount is recalculated. An AMEX purchase remains an
unassigned procurement assertion; it is not Job material consumption. Settlement
does not duplicate accrual revenue. Operational entities remain context rather than
financial measurements.

The readiness assessment covers revenue, direct labor, direct material, equipment,
truck and overhead. Present QBO evidence can make revenue-shaped or purchase-shaped
evidence `PARTIAL`, never complete or accepted. Missing source categories remain
`UNKNOWN`, never zero. A partial QBO acquisition downgrades affected readiness to
`UNKNOWN` and lists `complete_source_manifest` as missing.

This bridge is deterministic and provider-neutral at its consumer boundary. It
does not query QBO, mutate source evidence, write Accounting or operational tables,
create persistence, publish dashboards, allocate costs, compute margin, resolve HCP
conflicts, or authorize BE.9. After real acquisition, it can classify evidence
immediately; Economics still requires accepted source-domain facts and Finance
policy before calculating measured profitability.

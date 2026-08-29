# BANK.BEA.007A — Native financial workflow and Accounting control signals

## Boundary

BANK.BEA.007A adds twelve definition-bound, deterministic Beacon signal types for
explicit ACP-native financial workflow and Accounting control exceptions. It extends
the accepted Beacon catalog architecture without changing the immutable 21-definition
BANK.BEA.001 operational cohort or its identities. The combined internal registry is
used by quality, prioritization, workflow, and escalation services; the read-only
`GET /api/v1/beacon/financial-control-catalog` projection keeps classification
explicit for clients.

The adapter boundary is `NativeFinancialFact`. An owning ACP domain supplies Company,
optional Branch, source aggregate, authoritative evidence identities and digest,
deterministic as-of/cutoff context, and only the definition-required native state.
Beacon does not query raw Migration evidence and the source enum cannot represent QBO,
HCP, Economics, or another provider assertion. Conflicting accepted evidence fails
closed. Descriptions, dates, amounts, and proximity never establish identity.

## Catalog

| Definition | Classification | Accepted condition |
| --- | --- | --- |
| `financial.invoice.workflow_exception` | `NATIVE_FINANCIAL_WORKFLOW` | Explicit reconciliation-required, failed handoff, or invalid lifecycle evidence |
| `financial.receivable.strict_past_due` | `NATIVE_FINANCIAL_WORKFLOW` | Open native receivable, contractual due date before deterministic as-of, positive open amount |
| `financial.payment.evidence_inconsistency` | `NATIVE_FINANCIAL_WORKFLOW` | Explicit native reconciliation-required or durable Payments inconsistency |
| `financial.payment.application_mismatch` | `ACCOUNTING_CONTROL` | Explicit native invariant failure with accepted reconciliation identity |
| `financial.payment.unapplied` | `NATIVE_FINANCIAL_WORKFLOW` | Native unapplied receipt with positive available amount |
| `financial.ap.bill_workflow_exception` | `NATIVE_FINANCIAL_WORKFLOW` | Explicit rejected, reconciliation-required, or failed AP posting workflow |
| `accounting.posting.failure` | `ACCOUNTING_CONTROL` | Durable `PostingFailure` with correlation/reconciliation identity |
| `accounting.journal.rejected_or_integrity_failed` | `ACCOUNTING_CONTROL` | Durable rejected/integrity-failed journal evidence |
| `accounting.reconciliation.exception` | `ACCOUNTING_CONTROL` | Explicit unreconciled/reconciliation-required state with compatible scope and cutoff identity |
| `accounting.report.completeness_failure` | `ACCOUNTING_CONTROL` | Produced ACC.RPT result explicitly marked incomplete |
| `accounting.report.integrity_failure` | `ACCOUNTING_CONTROL` | Durable report integrity/provenance failure |
| `accounting.period.control_violation` | `ACCOUNTING_CONTROL` | Durable closed-period, period-bound, or exact cutoff-control rejection |

Signal identity is UUIDv5 over the BANK.BEA.007A catalog/definition digests, Company,
Branch, subject, accepted evidence identities, and evidence digest. Condition identity
excludes changing evidence so acknowledgement and ownership remain attached to the
continuing source condition. Re-evaluation with identical facts is identical; changed
accepted evidence creates deterministic replacement evidence. Clearing the native
predicate produces no current signal and cannot be requested through Beacon.

## Quality, priority, workflow, and escalation

Durable events and deterministic as-of conclusions use
`EvidenceFreshnessState.NOT_APPLICABLE`; this is a temporal contract, not a fabricated
freshness window. They still require complete, reconciled, non-conflicting accepted
evidence. Report freshness is excluded.

BANK.BEA.004 ordering remains severity, definition priority band, approved urgency,
then stable UUID. None of these definitions has an urgency policy, and raw amounts are
not emitted as ranking facts. The legacy invoice exposure evaluator remains outside
this queue.

Generated signals use the existing `BeaconSignal`, condition key, lifecycle, workflow,
and operational prioritizer contracts. BANK.BEA.005 acknowledgement/claim/assignment/
transfer/release changes workflow only. All twelve escalation registrations are
`POLICY_MISSING`; BANK.BEA.006 freshness TTLs are not reused as escalation durations.

## Explicit exclusions

BANK.BEA.007B remains deferred for aging/grace, freshness, acceptance, tolerance,
cutoff interpretation, recognition, materiality, review, and source-precedence policy.
BANK.BEA.007C remains deferred for QBO/HCP discrepancies. Contribution, margin,
profitability, leakage, and economic materiality require a separately approved
Beacon/ECO milestone. No evaluator mutates invoices, payments, bills, journals,
periods, reconciliation, source evidence, notification delivery, or another domain.

No schema or migration is introduced. Financial and Accounting domains retain their
existing persistence; Beacon quality, priority, lifecycle, and workflow remain
deterministically derived or use the existing Beacon persistence.

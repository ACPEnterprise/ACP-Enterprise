# ECO.EVIDENCE.ACCEPTANCE.1

## Boundary

All County Finance Policy v1 states what Finance would accept. This milestone defines how ACP proves that qualifying evidence exists. A policy choice, source payload, adapter output, or convenient field cannot approve itself. Evidence closes a gap only through the exact versioned acceptance contract and an explicit, digest-bound acceptance grant.

No economic value is calculated here. Missing evidence remains `OPEN`; different accepted value digests produce `CONFLICTING`; replacement appends `SUPERSEDED` evidence without rewriting history.

## Acceptance domains

- **Job lifecycle:** ACP Jobs can authoritatively identify the Job and its current completed state. Immutable lifecycle events must establish completion time, reopen/recompletion, cancellation, and supersession.
- **Earned value:** billing, estimates, payments, HCP amounts, and QBO amounts do not establish earned value. ACP still needs a Finance-accepted earned-value revision/correction contract.
- **Actual labor:** scheduled or elapsed appointments are not actual Job time. ACP still needs approved participation/time revisions, approval, correction, and multi-worker identity.
- **Worker-class burden:** Finance must approve effective-dated classes, assignments, rates/bases, and true-up rules. Selection of the standard-burden strategy supplies none of those values.
- **Materials:** ACP inventory issues and reversals preserve issue history, but the current reservation `demand_type`/`demand_id` seam does not itself prove an authoritative Job relationship. A typed, validated Job-demand contract and accepted cost-layer valuation are separate prerequisites. Purchases and AP do not establish Job consumption.
- **Other direct cost:** ACP needs approved categories plus authoritative Job linkage, accepted value, effective date, and correction/reversal evidence. No category list is selected here.
- **Conflicts:** all assertions remain preserved; unresolved different accepted values exclude the component and prevent complete admission. There is no source precedence.
- **Accounting quality:** a versioned attestation must separately prove completeness, freshness, reconciliation, integrity, and review state. Policy-permitted pending review remains `UNREVIEWED / PROVISIONAL` through prerequisites and packages.

## Source-authority matrix

| Evidence type | Current ACP role | Accounting role | HCP role | QBO role | Current state |
|---|---|---|---|---|---|
| Job lifecycle | ACP Jobs authority after accepted identity/cutover | Not required | Migration provenance only | Not authoritative | Available/partial contract qualification |
| Earned Job value | No accepted earned-value contract | Posting facts do not prove Job earned meaning | Source-reported | `quickbooks_online_source_reported` | Missing contract |
| Actual Job time | No approved actual-time ledger | Not applicable | Public operational evidence only | Not authoritative | Missing contract |
| Worker-class burden | Finance parameters absent | Not applicable | Not authoritative | Not authoritative | Missing Finance parameters |
| Job material | Inventory issue/linkage partially available | Posting/cost alone insufficient | Source-reported | `quickbooks_online_source_reported` | Partial; cost acceptance missing |
| Other direct cost | No accepted category/link/value contract | Posting facts alone insufficient | Source-reported | `quickbooks_online_source_reported` | Missing contract |
| Accounting quality | No aggregate quality attestation | Must attest completeness/currentness/reconciliation/integrity/review | Control evidence only | `quickbooks_online_source_reported` | Missing contract/reconciliation |

Neither HCP nor QBO is promoted by these contracts. Accounting provenance is distinct from Job-level economic meaning.

## All County v1 gap assessment

| Policy family | Gap | Classification |
|---|---|---|
| Job lifecycle | `authoritative_completed_status` | `SATISFIABLE_NOW` |
| Job lifecycle | `reopen_recompletion_treatment` | `SATISFIABLE_NOW` |
| Revenue | `accepted_earned_job_value` | `UPSTREAM_CONTRACT_REQUIRED` |
| Revenue | `revenue_corrections` | `UPSTREAM_CONTRACT_REQUIRED` |
| Direct labor | `approved_actual_job_time` | `UPSTREAM_CONTRACT_REQUIRED` |
| Direct labor | `technician_participation_identity` | `UPSTREAM_CONTRACT_REQUIRED` |
| Direct labor | `labor_approval_correction` | `UPSTREAM_CONTRACT_REQUIRED` |
| Direct labor | `multi_technician_participation` | `UPSTREAM_CONTRACT_REQUIRED` |
| Labor burden | `worker_class_definitions` | `FINANCE_PARAMETER_REQUIRED` |
| Labor burden | `worker_class_assignments` | `FINANCE_PARAMETER_REQUIRED` |
| Labor burden | `standard_burden_rates` | `FINANCE_PARAMETER_REQUIRED` |
| Labor burden | `burden_true_up` | `FINANCE_PARAMETER_REQUIRED` |
| Materials | `job_linked_inventory_issues` | `UPSTREAM_CONTRACT_REQUIRED` |
| Materials | `inventory_cost_layers` | `UPSTREAM_CONTRACT_REQUIRED` |
| Materials | `material_corrections` | `SATISFIABLE_NOW` |
| Other direct cost | `direct_cost_categories` | `FINANCE_PARAMETER_REQUIRED` |
| Other direct cost | `direct_cost_job_linkage` | `UPSTREAM_CONTRACT_REQUIRED` |
| Other direct cost | `direct_cost_value_authority` | `UPSTREAM_CONTRACT_REQUIRED` |
| Conflict | `conflict_identity` | `SATISFIABLE_NOW` |
| Conflict | `conflict_exclusion` | `SATISFIABLE_NOW` |
| Accounting quality | `accounting_completeness` | `UPSTREAM_CONTRACT_REQUIRED` |
| Accounting quality | `accounting_freshness` | `UPSTREAM_CONTRACT_REQUIRED` |
| Accounting quality | `accounting_reconciliation` | `EXTERNAL_RECONCILIATION_REQUIRED` |
| Accounting quality | `accounting_integrity` | `UPSTREAM_CONTRACT_REQUIRED` |
| Accounting quality | `provisional_review_label` | `UPSTREAM_CONTRACT_REQUIRED` |

`SATISFIABLE_NOW` means an accepted ACP public contract can provide the required shape; it does not mean any real gap was closed by this milestone.

## Deterministic closure and replay

The acceptance contract digest binds required facts, allowed authority, prohibited evidence roles, provisional behavior, family, gap, and version. The grant digest binds approval, Company/Branch/subject, exact evidence digest, authority, contract/version, and effective interval. The closure digest binds gap, scope, reconciliation key, effective/as-of context, accepted evidence identities/digests, authority, lifecycle state, provisional label, limitations, and supersession lineage.

The readiness bridge resolves a policy prerequisite only when every registered gap for that policy family is satisfied in a verified, scope-matching closure snapshot. A conflicting, open, absent, or superseded closure remains blocking. A synthetic fully accepted path can therefore become `MEASURABLE` and `ADMITTED`; no calculation follows admission.

## Dependency map

1. `ECO.JOB.LIFECYCLE.ACCEPTANCE.1`: qualify native Job completion/lifecycle-event adapters.
2. `ECO.INVENTORY.JOB.CONSUMPTION.AUTHORITY.1`: add typed, validated Job-demand linkage and qualify issue/reversal adapters; leave valuation blocked.
3. `ECO.EARNED.VALUE.AUTHORITY.1`: add accepted earned-value revisions, credits/adjustments, cancellations, and correction lineage.
4. `ECO.ACTUAL.JOB.TIME.AUTHORITY.1`: add approved actual participation/time and correction history.
5. `ECO.INVENTORY.COST.ACCEPTANCE.1`: establish accepted issue cost layers and costing provenance.
6. `ECO.DIRECT.COST.AUTHORITY.1`: after category approval, add Job linkage and accepted cost revisions.
7. `ECO.ACCOUNTING.QUALITY.ATTESTATION.1`: establish complete/current/reconciled/integrity/review attestations.
8. Finance parameter activation: separately approve worker classes, assignments, rates, true-up, and direct-cost categories.
9. External reconciliation: close the QBO/HCP/Accounting reconciliation gate after authoritative evidence is available.

Technician Economics remains separate: actual compensation, payroll costs, vehicles, tools/assets, worker-period attribution, and multi-technician revenue attribution cannot be replaced by Job Economics standard worker-class burden.

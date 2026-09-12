# Payroll compensation proration owner decision

Status: **OWNER POLICY REQUIRED**. No All County policy is selected by this candidate.

## Why a decision is required

When an hourly Employee has more than one approved compensation authority effective inside one Payroll period, Payroll cannot safely use one period-wide rate. The selected policy controls which approved authority applies to each accepted time fact. Until an approved policy exists, period assembly fails closed.

## Supported choices

| Choice | Result | Evidence used |
| --- | --- | --- |
| `BLOCK_PAYROLL` | Keep affected periods blocked for explicit resolution. | Approved compensation authorities and the detected effective-date change. |
| `BY_WORK_DATE` | Map each accepted payable time fact to the one current hourly compensation authority on its authoritative work date. | Accepted time revision/work date plus approved effective-dated compensation lineage. |

`UNSELECTED` records that the owner has not decided; it cannot be approved and never acts as a default.

Proration by accepted timestamp or period segment is not offered because current accepted Payroll time is authoritative by `work_date`, not as divisible intraday payable units. Salaried and other non-hourly proration remains `POLICY_REQUIRED / SOURCE_REQUIRED`; no salary semantics are inferred.

## Synthetic example

For an Aug 29–Sep 4 period, suppose synthetic accepted time is 120 minutes on Aug 31 and 180 minutes on Sep 1, with synthetic hourly authorities changing from $30 to $32 effective Sep 1. `BY_WORK_DATE` binds the Aug 31 fact to authority version 1 and Sep 1 to version 2. `BLOCK_PAYROLL` produces no payable allocation. This example is not All County policy or real Employee time.

## Consequences

The approved choice is Company-scoped, effective-dated, versioned, separately approved, provenance-bound, digest-bound, and superseded without rewriting history. Corrections must be reassembled from the current accepted time evidence; predecessors contribute zero. Tax calculation, Payroll execution, Accounting posting, and money movement remain downstream and untouched.


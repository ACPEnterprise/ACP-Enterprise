"""Bridge resolved Finance policy into existing measurement prerequisites."""

from collections.abc import Mapping

from .measurement_contract import (
    MeasurementComponent,
    PolicyPrerequisite,
    PrerequisiteState,
)
from .policy_authority import PolicySnapshot, missing_required_parameters

_COMPONENT_BY_FAMILY: Mapping[str, MeasurementComponent] = {
    "job_lifecycle_cutoff": MeasurementComponent.JOB_CONTEXT,
    "revenue_recognition": MeasurementComponent.REVENUE_EARNED_VALUE,
    "payment_settlement_acceptance": MeasurementComponent.SETTLEMENT,
    "direct_labor_measurement": MeasurementComponent.DIRECT_LABOR,
    "labor_burden": MeasurementComponent.LABOR_BURDEN,
    "direct_material_costing": MeasurementComponent.DIRECT_MATERIAL,
    "other_attributable_direct_costs": MeasurementComponent.OTHER_DIRECT_COST,
    "overhead_pool_definitions": MeasurementComponent.OVERHEAD_ALLOCATION,
    "overhead_allocation": MeasurementComponent.OVERHEAD_ALLOCATION,
    "accounting_reconciliation_admission": MeasurementComponent.ACCOUNTING_RECONCILIATION,
}


def policy_snapshot_to_prerequisites(
    snapshot: PolicySnapshot,
) -> tuple[PolicyPrerequisite, ...]:
    snapshot.verify()
    prerequisites = []
    for policy in snapshot.policies:
        component = _COMPONENT_BY_FAMILY.get(policy.family_key)
        if component is None:
            continue
        resolved = (
            policy.family_key not in snapshot.deferred_family_keys
            and not missing_required_parameters(policy)
        )
        prerequisites.append(
            PolicyPrerequisite(
                dependency_id=policy.family_key,
                component=component,
                state=PrerequisiteState.RESOLVED
                if resolved
                else PrerequisiteState.UNRESOLVED,
                authority="company_finance_policy_authority",
                policy_version=f"{policy.definition_version}:{policy.policy_version}"
                if resolved
                else None,
                evidence_digest=policy.policy_digest if resolved else None,
            )
        )
    return tuple(sorted(prerequisites, key=lambda item: item.dependency_id))

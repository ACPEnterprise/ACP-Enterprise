"""Persistence boundary for approved Company Finance policy bundles."""

from sqlalchemy.ext.asyncio import AsyncSession

from .company_policy_configurations.all_county_v1 import AllCountyPolicyV1Bundle
from .models import (
    CompanyFinancePolicyGap,
    CompanyFinancePolicyVersion,
    FinancePolicySnapshotRecord,
)


class PolicyConfigurationPersistenceError(ValueError):
    pass


async def persist_all_county_policy_v1(
    session: AsyncSession, bundle: AllCountyPolicyV1Bundle
) -> None:
    """Persist one explicitly built bundle; never discovers or defaults a tenant."""
    bundle.snapshot.verify()
    if any(policy.company_id != bundle.company_id for policy in bundle.policies):
        raise PolicyConfigurationPersistenceError("policy bundle Company mismatch")
    for policy in bundle.policies:
        session.add(
            CompanyFinancePolicyVersion(
                id=policy.policy_id,
                company_id=policy.company_id,
                branch_id=None,
                family_key=policy.family_key,
                policy_version=policy.policy_version,
                strategy_key=policy.strategy_key,
                disposition=policy.disposition.value,
                parameters=dict(policy.parameters),
                evidence_acceptance_rule_refs=list(
                    policy.evidence_acceptance_rule_refs
                ),
                effective_start=policy.effective_start,
                effective_end=policy.effective_end,
                lifecycle=policy.lifecycle.value,
                definition_version=policy.definition_version,
                decision_evidence_digest=policy.decision_evidence_digest,
                policy_digest=policy.policy_digest,
                supersedes_policy_id=policy.supersedes_policy_id,
                drafted_by_user_id=bundle.approver_user_id,
                approved_by_user_id=policy.approved_by_user_id,
                approved_at=policy.approved_at,
                retired_by_user_id=None,
                retired_at=None,
                audit_reason=f"Activate {bundle.configuration_id} from owner-approved decision evidence",
            )
        )
    for gap in bundle.parameter_gaps:
        session.add(
            CompanyFinancePolicyGap(
                id=gap.gap_id,
                company_id=gap.company_id,
                branch_id=None,
                family_key=gap.family_key,
                gap_key=gap.gap_key,
                requirement=gap.requirement,
                authority_dependency=gap.authority_dependency,
                effective_start=gap.effective_start,
                state="open",
                decision_evidence_digest=gap.decision_evidence_digest,
                gap_digest=gap.gap_digest,
                registered_by_user_id=gap.registered_by_user_id,
                registered_at=gap.registered_at,
            )
        )
    snapshot = bundle.snapshot
    session.add(
        FinancePolicySnapshotRecord(
            company_id=snapshot.company_id,
            branch_id=None,
            subject_identity=snapshot.subject_identity,
            reconciliation_key=snapshot.reconciliation_key,
            as_of_date=snapshot.as_of,
            policy_ids=[str(policy.policy_id) for policy in snapshot.policies],
            policy_digests=[policy.policy_digest for policy in snapshot.policies],
            deferred_family_keys=list(snapshot.deferred_family_keys),
            parameter_gap_digests=[gap.gap_digest for gap in snapshot.parameter_gaps],
            definition_version=snapshot.definition_version,
            snapshot_digest=snapshot.snapshot_digest,
            created_by_user_id=bundle.approver_user_id,
        )
    )
    await session.flush()

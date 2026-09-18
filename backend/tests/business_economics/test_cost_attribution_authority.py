from datetime import date, datetime, timezone
from uuid import uuid4

from app.business_economics.cost_attribution_authority import (
    CertificationState,
    certification_state,
    decision_packet,
)
from app.business_economics.policy_authority import (
    POLICY_DEFINITION_VERSION,
    PolicyDisposition,
    PolicyLifecycle,
    missing_required_parameters,
    seal_policy,
)


def policy(*, company_id, family_key, lifecycle):
    approver = uuid4() if lifecycle is not PolicyLifecycle.DRAFT else None
    approved_at = datetime(2026, 9, 1, tzinfo=timezone.utc) if approver else None
    return seal_policy(
        policy_id=uuid4(),
        company_id=company_id,
        branch_id=None,
        family_key=family_key,
        policy_version=1,
        disposition=PolicyDisposition.SELECTED,
        strategy_key="hold_unallocated",
        parameters={},
        evidence_acceptance_rule_refs=(),
        effective_start=date(2026, 9, 1),
        effective_end=None,
        lifecycle=lifecycle,
        definition_version=POLICY_DEFINITION_VERSION,
        approved_by_user_id=approver,
        approved_at=approved_at,
        decision_evidence_digest="a" * 64,
        supersedes_policy_id=None,
    )


def test_unselected_decision_packet_does_not_choose_policy() -> None:
    company = uuid4()
    packet = decision_packet(
        (),
        company_id=company,
        family_key="overtime_premium_allocation",
        as_of=date(2026, 9, 15),
    )
    assert packet["certification_state"] == "unselected"
    assert packet["selection"] is None
    assert packet["mutation_authority"] == "none"
    assert "hold_unallocated" in packet["supported_choices"]


def test_draft_never_projects_as_certified() -> None:
    company = uuid4()
    draft = policy(
        company_id=company,
        family_key="overtime_premium_allocation",
        lifecycle=PolicyLifecycle.DRAFT,
    )
    assert (
        certification_state(
            (draft,),
            company_id=company,
            family_key=draft.family_key,
            as_of=date(2026, 9, 15),
        )
        is CertificationState.DRAFT
    )


def test_only_effective_approved_policy_projects_as_certified() -> None:
    company = uuid4()
    approved = policy(
        company_id=company,
        family_key="overtime_premium_allocation",
        lifecycle=PolicyLifecycle.APPROVED,
    )
    assert (
        certification_state(
            (approved,),
            company_id=company,
            family_key=approved.family_key,
            as_of=date(2026, 9, 15),
        )
        is CertificationState.CERTIFIED
    )
    assert (
        certification_state(
            (approved,),
            company_id=company,
            family_key=approved.family_key,
            as_of=date(2026, 8, 31),
        )
        is CertificationState.UNSELECTED
    )


def test_component_specific_burden_requires_certified_reference_list() -> None:
    company = uuid4()
    candidate = seal_policy(
        policy_id=uuid4(),
        company_id=company,
        branch_id=None,
        family_key="employer_burden_allocation",
        policy_version=1,
        disposition=PolicyDisposition.SELECTED,
        strategy_key="component_specific_certified_drivers",
        parameters={},
        evidence_acceptance_rule_refs=(),
        effective_start=date(2026, 9, 1),
        effective_end=None,
        lifecycle=PolicyLifecycle.APPROVED,
        definition_version=POLICY_DEFINITION_VERSION,
        approved_by_user_id=uuid4(),
        approved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        decision_evidence_digest="b" * 64,
        supersedes_policy_id=None,
    )
    candidate.validate()
    assert missing_required_parameters(candidate) == ("component_driver_refs",)

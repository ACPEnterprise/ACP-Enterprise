from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest
from app.business_economics.policy_authority import (
    POLICY_DEFINITION_VERSION,
    POLICY_FAMILY_REGISTRY,
    CompanyPolicyVersion,
    PolicyAuthorizationError,
    PolicyIntegrityError,
    PolicyLifecycle,
    PolicyResolutionError,
    PolicySnapshot,
    build_policy_snapshot,
    require_policy_permission,
    resolve_policy,
    seal_policy,
    validate_policy_set,
)


def policy(
    company_id: UUID,
    *,
    version: int = 1,
    start: date = date(2026, 1, 1),
    end: date | None = None,
    family: str = "revenue_recognition",
) -> CompanyPolicyVersion:
    return seal_policy(
        policy_id=uuid4(),
        company_id=company_id,
        branch_id=None,
        family_key=family,
        policy_version=version,
        strategy_key="synthetic_strategy",
        parameters={"synthetic": True},
        evidence_acceptance_rule_refs=("acceptance:test:v1",),
        effective_start=start,
        effective_end=end,
        lifecycle=PolicyLifecycle.APPROVED,
        definition_version=POLICY_DEFINITION_VERSION,
        approved_by_user_id=uuid4(),
        approved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        decision_evidence_digest="a" * 64,
        supersedes_policy_id=None,
    )


def test_registry_contains_required_product_families() -> None:
    assert len(POLICY_FAMILY_REGISTRY) == 12
    assert "accounting_reconciliation_admission" in POLICY_FAMILY_REGISTRY


def test_resolution_is_company_scoped_and_deterministic() -> None:
    first, second = uuid4(), uuid4()
    one, other = policy(first), policy(second)
    assert (
        resolve_policy(
            [other, one],
            company_id=first,
            family_key="revenue_recognition",
            as_of=date(2026, 2, 1),
        )
        == one
    )
    with pytest.raises(PolicyResolutionError):
        resolve_policy(
            [other],
            company_id=first,
            family_key="revenue_recognition",
            as_of=date(2026, 2, 1),
        )


def test_overlap_and_branch_override_fail_closed() -> None:
    company = uuid4()
    with pytest.raises(PolicyResolutionError):
        resolve_policy(
            [policy(company), policy(company, version=2)],
            company_id=company,
            family_key="revenue_recognition",
            as_of=date(2026, 2, 1),
        )
    with pytest.raises(PolicyResolutionError):
        resolve_policy(
            [policy(company)],
            company_id=company,
            branch_id=uuid4(),
            family_key="revenue_recognition",
            as_of=date(2026, 2, 1),
        )
    with pytest.raises(PolicyIntegrityError):
        validate_policy_set([policy(company), policy(company, version=2)])


def test_only_explicitly_approved_policy_resolves() -> None:
    company = uuid4()
    approved = policy(company)
    draft = CompanyPolicyVersion(
        **{**approved.__dict__, "lifecycle": PolicyLifecycle.DRAFT, "policy_digest": ""}
    )
    with pytest.raises(PolicyIntegrityError):
        resolve_policy(
            [draft],
            company_id=company,
            family_key="revenue_recognition",
            as_of=date(2026, 2, 1),
        )


def test_snapshot_is_deterministic_immutable_and_replayable() -> None:
    company = uuid4()
    policies = [policy(company), policy(company, family="direct_labor_measurement")]

    def build(values: list[CompanyPolicyVersion]) -> PolicySnapshot:
        return build_policy_snapshot(
            values,
            company_id=company,
            branch_id=None,
            subject_identity="job:synthetic",
            reconciliation_key="job:test",
            as_of=date(2026, 2, 1),
            required_families=(
                "revenue_recognition",
                "direct_labor_measurement",
            ),
        )

    first = build(policies)
    second = build(list(reversed(policies)))
    assert first.snapshot_digest == second.snapshot_digest
    first.verify()
    tampered = CompanyPolicyVersion(
        **{**policies[0].__dict__, "strategy_key": "changed"}
    )
    with pytest.raises(PolicyIntegrityError):
        tampered.validate()


def test_evidence_acceptance_reference_does_not_promote_authority() -> None:
    value = policy(uuid4())
    assert value.evidence_acceptance_rule_refs == ("acceptance:test:v1",)
    assert "authority" not in value.parameters


def test_append_only_supersession_preserves_historical_replay() -> None:
    company = uuid4()
    original = policy(company)
    successor = seal_policy(
        policy_id=uuid4(),
        company_id=company,
        branch_id=None,
        family_key="revenue_recognition",
        policy_version=2,
        strategy_key="new_synthetic_strategy",
        parameters={},
        evidence_acceptance_rule_refs=(),
        effective_start=date(2026, 7, 1),
        effective_end=None,
        lifecycle=PolicyLifecycle.APPROVED,
        definition_version=POLICY_DEFINITION_VERSION,
        approved_by_user_id=uuid4(),
        approved_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        decision_evidence_digest="b" * 64,
        supersedes_policy_id=original.policy_id,
    )
    validate_policy_set([original, successor])
    assert (
        resolve_policy(
            [original, successor],
            company_id=company,
            family_key="revenue_recognition",
            as_of=date(2026, 6, 30),
        )
        == original
    )
    assert (
        resolve_policy(
            [original, successor],
            company_id=company,
            family_key="revenue_recognition",
            as_of=date(2026, 7, 1),
        )
        == successor
    )


def test_policy_actions_have_separate_authorization_boundaries() -> None:
    require_policy_permission("draft", frozenset({"COMPANY_ECONOMICS_POLICY_DRAFT"}))
    with pytest.raises(PolicyAuthorizationError):
        require_policy_permission(
            "approve", frozenset({"COMPANY_ECONOMICS_POLICY_DRAFT"})
        )

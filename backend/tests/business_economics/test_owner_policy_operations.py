from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from app.business_economics.break_even_calculation import (
    CalculationState,
    calculate_governed_break_even,
)
from app.business_economics.break_even_operator_readiness import (
    BlockerGroup,
    OperatorReadinessState,
    build_operator_readiness,
    preview_draft_policy,
)
from app.business_economics.break_even_policy import (
    BreakEvenPolicyKind,
    PolicyApprovalState,
    PolicyApproverRole,
)
from app.business_economics.owner_policy_operations import (
    InMemoryPolicyOperationRepository,
    OwnerPolicyOperationsService,
    PolicyActor,
    policy_operation_audit_entry,
)
from app.business_economics.policy_authority import PolicyAuthorizationError

from tests.business_economics.test_break_even_calculation_explanation import (
    START,
    _facts,
    _policy,
)

NOW = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)


def _actor(*permissions: str, company_id=None, branch_id=None):
    return PolicyActor(
        uuid4(),
        company_id or uuid4(),
        branch_id,
        frozenset(permissions),
        PolicyApproverRole.OWNER,
    )


def _draft(
    service, actor, *, value=Decimal("0.25"), kind=BreakEvenPolicyKind.CAPACITY_BUFFER
):
    return service.draft(
        actor,
        kind=kind,
        value=value,
        effective_start=START,
        provenance="owner_workspace",
        provenance_digest="a" * 64,
        rationale="qualification draft",
        occurred_at=NOW,
    )


def test_draft_submit_approval_and_authoritative_version_are_distinct() -> None:
    repository = InMemoryPolicyOperationRepository()
    service = OwnerPolicyOperationsService(repository)
    actor = _actor(
        "COMPANY_ECONOMICS_POLICY_READ",
        "COMPANY_ECONOMICS_POLICY_DRAFT",
        "COMPANY_ECONOMICS_POLICY_APPROVE",
    )
    draft = _draft(service, actor)
    assert draft.state is PolicyApprovalState.DRAFT
    listed = service.list_families(actor, as_of=START)
    capacity = next(x for x in listed["families"] if x["family"] == "capacity_buffer")
    assert capacity["state"] == "DRAFT"
    before_effective = service.list_families(actor, as_of=date(2026, 8, 31))
    before_capacity = next(
        x for x in before_effective["families"] if x["family"] == "capacity_buffer"
    )
    assert before_capacity["state"] == "UNSELECTED"
    submitted = service.submit(
        actor, policy_id=draft.policy_id, rationale="submit", occurred_at=NOW
    )
    assert submitted.state is PolicyApprovalState.AWAITING_APPROVAL
    approved = service.approve(
        actor, policy_id=draft.policy_id, rationale="approve", occurred_at=NOW
    )
    assert approved.state is PolicyApprovalState.APPROVED
    assert approved.policy.approved_by_user_id == actor.user_id
    audit = policy_operation_audit_entry(approved)
    assert audit.company_id == actor.company_id
    assert audit.details["policy_digest"] == approved.policy.policy_digest
    assert len(service.history(actor)) == 3
    assert service.list_families(actor, as_of=START)["families"]


def test_unauthorized_and_foreign_scope_mutation_fail_closed() -> None:
    repository = InMemoryPolicyOperationRepository()
    service = OwnerPolicyOperationsService(repository)
    reader = _actor("COMPANY_ECONOMICS_POLICY_READ")
    with pytest.raises(PolicyAuthorizationError):
        _draft(service, reader)
    manager = _actor("COMPANY_ECONOMICS_POLICY_DRAFT")
    draft = _draft(service, manager)
    foreign = _actor("COMPANY_ECONOMICS_POLICY_DRAFT")
    with pytest.raises(ValueError, match="authorized scope"):
        service.submit(
            foreign, policy_id=draft.policy_id, rationale="foreign", occurred_at=NOW
        )


def test_supersession_preserves_history_and_effective_selection() -> None:
    repository = InMemoryPolicyOperationRepository()
    service = OwnerPolicyOperationsService(repository)
    actor = _actor(
        "COMPANY_ECONOMICS_POLICY_READ",
        "COMPANY_ECONOMICS_POLICY_DRAFT",
        "COMPANY_ECONOMICS_POLICY_APPROVE",
    )
    first = _draft(service, actor, value=Decimal("0.10"))
    service.submit(
        actor, policy_id=first.policy_id, rationale="submit 1", occurred_at=NOW
    )
    service.approve(
        actor, policy_id=first.policy_id, rationale="approve 1", occurred_at=NOW
    )
    second = _draft(service, actor, value=Decimal("0.20"))
    service.submit(
        actor, policy_id=second.policy_id, rationale="submit 2", occurred_at=NOW
    )
    service.approve(
        actor, policy_id=second.policy_id, rationale="approve 2", occurred_at=NOW
    )
    history = service.history(actor)
    assert any(
        x.policy_id == first.policy_id and x.state is PolicyApprovalState.SUPERSEDED
        for x in history
    )
    assert any(
        x.policy_id == first.policy_id and x.state is PolicyApprovalState.APPROVED
        for x in history
    )
    current = next(
        x
        for x in service.list_families(actor, as_of=START)["families"]
        if x["family"] == "capacity_buffer"
    )
    assert current["current_version"] == 2


def test_readiness_groups_accounting_and_calculation_blockers_deterministically() -> (
    None
):
    company = uuid4()
    calculation = calculate_governed_break_even(
        policy=_policy(company, omit=BreakEvenPolicyKind.LABOR_BURDEN_METHOD),
        measured_facts=_facts(company),
    )
    first = build_operator_readiness(calculation, accounting_reconciled=False)
    second = build_operator_readiness(calculation, accounting_reconciled=False)
    assert first == second
    assert first.state is OperatorReadinessState.BLOCKED
    groups = {x.group for x in first.blocker_groups}
    assert BlockerGroup.POLICY_UNSELECTED in groups
    assert BlockerGroup.ACCOUNTING_NOT_RECONCILED in groups
    ready_calculation = calculate_governed_break_even(
        policy=_policy(company), measured_facts=_facts(company)
    )
    assert ready_calculation.state is CalculationState.AVAILABLE
    assert (
        build_operator_readiness(ready_calculation, accounting_reconciled=True).state
        is OperatorReadinessState.READY
    )


def test_draft_preview_never_mutates_baseline_evidence_or_becomes_authoritative() -> (
    None
):
    company = uuid4()
    repository = InMemoryPolicyOperationRepository()
    service = OwnerPolicyOperationsService(repository)
    actor = _actor(
        "COMPANY_ECONOMICS_POLICY_READ",
        "COMPANY_ECONOMICS_POLICY_DRAFT",
        company_id=company,
    )
    draft = _draft(
        service,
        actor,
        kind=BreakEvenPolicyKind.TARGET_OPERATING_MARGIN,
        value=Decimal("0.30"),
    )
    facts = _facts(company)
    before = tuple((x.metric, x.value, x.evidence_digest) for x in facts)
    preview = preview_draft_policy(
        actor=actor,
        approved_policy=_policy(company),
        draft=draft.policy,
        measured_facts=facts,
    )
    after = tuple((x.metric, x.value, x.evidence_digest) for x in facts)
    assert before == after
    assert preview.authoritative is False
    assert preview.measured_evidence_unchanged
    assert (
        preview.approved_baseline.calculation_digest
        != preview.calculated_preview.calculation_digest
    )
    assert "DRAFT_POLICY" in preview.labels
    assert "CALCULATED_PREVIEW" in preview.labels
    assert draft.state is PolicyApprovalState.DRAFT
    assert (
        preview.approved_baseline.measurement_evidence_digests
        == preview.calculated_preview.measurement_evidence_digests
    )

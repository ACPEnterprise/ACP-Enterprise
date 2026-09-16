from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.lia.contracts import EvidenceReference, LiaContext, LiaRequest
from app.lia.payroll_guidance import payroll_guidance_answer
from app.lia.retrieval import GovernedRetrievalService
from app.lia.service import LiaService
from app.payroll.permissions import PayrollPermission
from app.platform.permissions.codes import WorkforcePermission

BLOCKERS = (
    "COMPENSATION_MISSING_CONFIGURATION",
    "GROSS_PAY_NOT_CALCULATED",
    "PAYROLL_POLICY_MISSING_CONFIGURATION",
    "TIME_EVIDENCE_MISSING",
    "WITHHOLDING_NOT_CALCULATED",
)


def _payroll_evidence(employee_id=None) -> EvidenceReference:
    employee_id = employee_id or uuid4()
    states = ", ".join(f"blocker:{code}" for code in BLOCKERS)
    return EvidenceReference(
        domain="payroll",
        label="Payroll readiness for Lianne Hernandez",
        authority="PAYROLL.PERIOD.OPERATIONS.v1",
        observed_at=datetime.now(timezone.utc),
        freshness="CURRENT_QUERY",
        entity_id=employee_id,
        evidence_digest="a" * 64,
        count=len(BLOCKERS),
        state=states,
        limitations=("protected_payroll_values_excluded",),
    )


def test_readiness_question_is_direct_and_prioritizes_first_owner_action() -> None:
    answer = payroll_guidance_answer(
        "Is Lianne Hernandez ready for payroll?", (_payroll_evidence(),)
    )
    assert answer is not None
    assert answer.startswith("No. Lianne Hernandez is not ready for Payroll")
    assert "5 recognized blockers" in answer
    assert "Set up and approve compensation basis" in answer


def test_blocker_question_groups_plain_english_responsibility() -> None:
    answer = payroll_guidance_answer(
        "What specifically is preventing Lianne from being payroll ready?",
        (_payroll_evidence(),),
    )
    assert answer is not None
    assert "Owner actions:" in answer
    assert "Source evidence required:" in answer
    assert "ACP calculations after prerequisites:" in answer
    assert "COMPENSATION_MISSING_CONFIGURATION" not in answer


def test_next_action_sequence_places_calculation_after_prerequisites() -> None:
    answer = payroll_guidance_answer(
        "What should I do next to make Lianne Hernandez payroll ready?",
        (_payroll_evidence(),),
    )
    assert answer is not None
    compensation = answer.index("Set up and approve compensation")
    policy = answer.index("Complete and approve the Company Payroll policy")
    time = answer.index("Enter or import the actual time evidence")
    withholding_authority = answer.index("Verify that approved W-4")
    gross = answer.index("Run gross-pay calculation")
    withholding = answer.index("run withholding calculation")
    rerun = answer.index("Re-run Payroll readiness")
    assert (
        compensation
        < policy
        < time
        < withholding_authority
        < gross
        < withholding
        < rerun
    )


def test_owner_and_accountant_follow_ups_do_not_invent_accountant_work() -> None:
    owner = payroll_guidance_answer(
        "Which of those steps can I complete myself?", (_payroll_evidence(),)
    )
    accountant = payroll_guidance_answer(
        "What still requires the accountant?", (_payroll_evidence(),)
    )
    after = payroll_guidance_answer(
        "What happens after I finish those?", (_payroll_evidence(),)
    )
    assert owner is not None and "You can work on these now" in owner
    assert "Run gross-pay calculation" not in owner
    assert (
        accountant is not None and "do not prove an accountant-only task" in accountant
    )
    assert "will not infer those values" in accountant
    assert after is not None
    assert after.index("gross-pay") < after.index("withholding")


@pytest.mark.asyncio
async def test_follow_up_chain_retains_employee_and_adds_no_mutation() -> None:
    employee_id = uuid4()
    payroll = _payroll_evidence(employee_id)
    workforce = EvidenceReference(
        domain="workforce",
        label="Minimum-necessary Workforce readiness context",
        authority="WORKFORCE.LIA_CONTEXT.v1",
        observed_at=payroll.observed_at,
        freshness="CURRENT_QUERY",
        entity_id=employee_id,
        evidence_digest="b" * 64,
        count=1,
        state="Employee Lianne Hernandez is active",
    )
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    retrieval.retrieve.return_value = (workforce, payroll)
    service = LiaService(retrieval=retrieval)
    branch_id = uuid4()
    context = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        membership=SimpleNamespace(id=uuid4()),
        company=SimpleNamespace(id=uuid4()),
        active_branch=SimpleNamespace(id=branch_id),
        authorized_branch_ids=frozenset({branch_id}),
        authorization_version=22,
        has_permission=lambda permission: (
            permission in {WorkforcePermission.READ, PayrollPermission.REPORTING_READ}
        ),
    )
    continuation = LiaContext(
        domain="workforce",
        entity_id=employee_id,
        authorization_version=22,
        topic_domains=("workforce", "payroll"),
    )
    for question in (
        "What should I do next to make Lianne Hernandez payroll ready?",
        "Which of those steps can I complete myself?",
        "What still requires the accountant?",
        "What happens after I finish those?",
    ):
        response = await service.ask(
            AsyncMock(),
            context=context,
            request=LiaRequest(question=question, context=continuation),
        )
        assert response.subject_id == employee_id
        assert response.proposals == ()
        assert "routing" not in response.answer.casefold()
        assert "bank account" not in response.answer.casefold()

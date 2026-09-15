from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.lia.contracts import (
    AnswerAuthority,
    EvidenceReference,
    LiaContext,
    LiaRequest,
    TruthClassification,
)
from app.lia.planner import QuestionIntent, plan_question
from app.lia.retrieval import GovernedRetrievalService
from app.lia.service import LiaService
from app.platform.permissions.codes import (
    AdministrationPermission,
    CustomerPermission,
    JobPermission,
)


def _context(*permissions: str) -> SimpleNamespace:
    branch_id = uuid4()
    return SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        membership=SimpleNamespace(id=uuid4()),
        company=SimpleNamespace(id=uuid4()),
        active_branch=SimpleNamespace(id=branch_id),
        authorized_branch_ids=frozenset({branch_id}),
        authorization_version=9,
        has_permission=lambda permission: permission in permissions,
    )


@pytest.mark.parametrize(
    ("question", "domains", "intent"),
    (
        (
            "Show this Customer's Jobs and payment history",
            {"customers", "jobs", "payments"},
            QuestionIntent.BUSINESS_STATUS,
        ),
        ("Why can't Payroll run?", {"payroll"}, QuestionIntent.PAYROLL_READINESS),
        (
            "Why can't I run a May financial report from QBO?",
            {"accounting"},
            QuestionIntent.ACCOUNTING_READINESS,
        ),
        ("What Beacon signals need attention?", {"beacon"}, QuestionIntent.ATTENTION),
        (
            "What remains before Production launch?",
            {"launch-readiness"},
            QuestionIntent.LAUNCH_READINESS,
        ),
    ),
)
def test_owner_question_planner_is_bounded(
    question: str, domains: set[str], intent: QuestionIntent
) -> None:
    plan = plan_question(question)
    assert set(plan.domains) == domains
    assert plan.intent is intent


@pytest.mark.asyncio
async def test_stale_authorization_fails_before_retrieval() -> None:
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    response = await LiaService(retrieval=retrieval).ask(
        AsyncMock(),
        context=_context(CustomerPermission.READ),
        request=LiaRequest(
            question="Show this Customer",
            context=LiaContext(
                domain="customers", entity_id=uuid4(), authorization_version=8
            ),
        ),
    )
    assert response.classification is TruthClassification.STALE
    assert response.authority is AnswerAuthority.INSUFFICIENT_EVIDENCE
    retrieval.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_source_backed_answer_is_not_promoted_to_acp_authority() -> None:
    now = datetime.now(timezone.utc)
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    retrieval.retrieve.return_value = (
        EvidenceReference(
            domain="migration",
            label="QBO source evidence",
            authority="AUTHORITATIVE_MIGRATION_EVIDENCE",
            observed_at=now,
            freshness="PERSISTED_EVIDENCE",
            evidence_digest="a" * 64,
            count=1,
            state="acquired=1",
        ),
    )
    response = await LiaService(retrieval=retrieval).ask(
        AsyncMock(),
        context=_context(AdministrationPermission.COMPANY_ADMINISTER),
        request=LiaRequest(question="What QBO source evidence exists?"),
    )
    assert response.authority is AnswerAuthority.SOURCE_BACKED
    assert response.company_id is not None
    assert response.source_systems == ("migration",)


@pytest.mark.asyncio
async def test_changed_context_digest_is_explicitly_stale() -> None:
    now = datetime.now(timezone.utc)
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    retrieval.retrieve.return_value = (
        EvidenceReference(
            domain="jobs",
            label="Job",
            authority="AUTHORITATIVE_FACT",
            observed_at=now,
            freshness="CURRENT_QUERY",
            evidence_digest="b" * 64,
            count=1,
            state="ready",
        ),
    )
    response = await LiaService(retrieval=retrieval).ask(
        AsyncMock(),
        context=_context(JobPermission.READ),
        request=LiaRequest(
            question="What happened on this Job?",
            context=LiaContext(
                domain="jobs",
                entity_id=uuid4(),
                authorization_version=9,
                evidence_digest="c" * 64,
            ),
        ),
    )
    assert response.classification is TruthClassification.STALE
    assert response.authority is AnswerAuthority.PARTIAL
    assert "silently" in response.limitations[0]


def test_lia_runtime_has_no_mutation_primitive() -> None:
    root = Path(__file__).resolve().parents[2] / "app" / "lia"
    text = "\n".join(path.read_text() for path in sorted(root.glob("*.py")))
    for forbidden in (
        "session.add(",
        "session.delete(",
        "session.commit(",
        "execute_payment",
        "schedule_appointment",
        "post_journal",
    ):
        assert forbidden not in text


def test_authority_contract_contains_required_owner_states() -> None:
    assert {item.value for item in AnswerAuthority} == {
        "ACP_AUTHORITATIVE",
        "SOURCE_BACKED",
        "PARTIAL",
        "INSUFFICIENT_EVIDENCE",
    }


def test_qualification_fingerprint_is_deterministic() -> None:
    root = Path(__file__).resolve().parents[3]
    payload = json.loads(
        (
            root
            / "docs/architecture/lia/owner-intelligence-readonly-qualification.v1.json"
        ).read_text()
    )
    expected = payload.pop("qualification_fingerprint")
    assert (
        expected
        == hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )

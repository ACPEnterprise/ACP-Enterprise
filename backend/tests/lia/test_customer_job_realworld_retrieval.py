from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from app.customers.lia_context import customer_lia_context_service
from app.jobs.lia_context import job_lia_context_service
from app.lia.contracts import (
    AnswerAuthority,
    EvidenceReference,
    LiaContext,
    LiaRequest,
    TruthClassification,
)
from app.lia.planner import plan_question
from app.lia.retrieval import GovernedRetrievalService
from app.lia.service import LiaService
from app.platform.permissions.codes import CustomerPermission, JobPermission


def _context(*permissions: str) -> SimpleNamespace:
    branch_id = uuid4()
    return SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        membership=SimpleNamespace(id=uuid4()),
        company=SimpleNamespace(id=uuid4()),
        active_branch=SimpleNamespace(id=branch_id),
        authorized_branch_ids=frozenset({branch_id}),
        authorization_version=14,
        has_permission=lambda permission: permission in permissions,
    )


def _evidence(domain: str, entity_id: UUID) -> EvidenceReference:
    contract = {
        "customers": "CUSTOMER.LIA_CONTEXT.v1",
        "jobs": "JOB.LIA_CONTEXT.v1",
    }[domain]
    return EvidenceReference(
        domain=domain,
        label=f"Minimum-necessary {domain} operational context",
        authority=contract,
        observed_at=datetime.now(timezone.utc),
        freshness="CURRENT_QUERY",
        entity_id=entity_id,
        evidence_digest=("c" if domain == "customers" else "j") * 64,
        count=1,
        state="authorized evidence",
        source_contract_version=contract,
    )


def test_named_customer_and_job_plans_are_bounded() -> None:
    customer = plan_question("Show me Customer Lianne Hernandez")
    assert customer.subject_domain == "customers"
    assert customer.subject_query == "Lianne Hernandez"
    assert customer.domains == frozenset({"customers"})

    natural = plan_question("Show me Lianne Hernandez")
    assert natural.subject_domain == "identity"
    assert natural.domains == frozenset({"customers", "workforce"})

    job = plan_question("Show me Job 306")
    assert job.subject_domain == "jobs"
    assert job.subject_query == "306"
    assert job.domains == frozenset({"jobs"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "domain", "permission", "resolver_name"),
    (
        (
            "Show me Customer Lianne Hernandez",
            "customers",
            CustomerPermission.READ,
            "resolve_display_name",
        ),
        ("Show me Job JOB-000306", "jobs", JobPermission.READ, "resolve_job_number"),
    ),
)
async def test_exact_authorized_subject_resolves_to_existing_projection(
    monkeypatch: pytest.MonkeyPatch,
    question: str,
    domain: str,
    permission: str,
    resolver_name: str,
) -> None:
    entity_id = uuid4()
    resolver_owner = (
        customer_lia_context_service
        if domain == "customers"
        else job_lia_context_service
    )
    monkeypatch.setattr(
        resolver_owner, resolver_name, AsyncMock(return_value=(entity_id,))
    )
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    retrieval.retrieve.return_value = (_evidence(domain, entity_id),)

    response = await LiaService(retrieval=retrieval).ask(
        AsyncMock(), context=_context(permission), request=LiaRequest(question=question)
    )

    assert response.classification is TruthClassification.KNOWN
    assert response.authority is AnswerAuthority.ACP_AUTHORITATIVE
    assert response.subject_domain == domain
    assert response.subject_id == entity_id
    assert response.proposals == ()
    assert retrieval.retrieve.await_args.kwargs["entity_id"] == entity_id
    assert retrieval.retrieve.await_args.kwargs["domains"] == {domain}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "domain", "permission", "matches"),
    (
        (
            "Show me Customer Same Name",
            "customers",
            CustomerPermission.READ,
            (uuid4(), uuid4()),
        ),
        ("Show me Job JOB-999999", "jobs", JobPermission.READ, ()),
    ),
)
async def test_ambiguous_and_missing_subjects_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    question: str,
    domain: str,
    permission: str,
    matches: tuple[UUID, ...],
) -> None:
    resolver_owner = (
        customer_lia_context_service
        if domain == "customers"
        else job_lia_context_service
    )
    resolver_name = (
        "resolve_display_name" if domain == "customers" else "resolve_job_number"
    )
    monkeypatch.setattr(resolver_owner, resolver_name, AsyncMock(return_value=matches))
    retrieval = AsyncMock(spec=GovernedRetrievalService)

    response = await LiaService(retrieval=retrieval).ask(
        AsyncMock(), context=_context(permission), request=LiaRequest(question=question)
    )

    assert response.classification is (
        TruthClassification.INCOMPLETE if matches else TruthClassification.UNAVAILABLE
    )
    assert response.evidence == ()
    assert response.proposals == ()
    retrieval.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_unauthorized_customer_lookup_hides_existence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = AsyncMock()
    monkeypatch.setattr(customer_lia_context_service, "resolve_display_name", resolver)
    retrieval = AsyncMock(spec=GovernedRetrievalService)
    response = await LiaService(retrieval=retrieval).ask(
        AsyncMock(),
        context=_context(JobPermission.READ),
        request=LiaRequest(question="Show me Customer Lianne Hernandez"),
    )
    assert response.classification is TruthClassification.UNAUTHORIZED
    resolver.assert_not_awaited()
    retrieval.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_customer_and_job_follow_ups_retain_authoritative_referent() -> None:
    for domain, questions in (
        (
            "customers",
            (
                "What work have we done for them?",
                "What invoices are unpaid?",
                "What is missing from their history?",
            ),
        ),
        (
            "jobs",
            (
                "Who is assigned?",
                "What happened on this job?",
                "Is it paid?",
                "What evidence is missing?",
            ),
        ),
    ):
        entity_id = uuid4()
        evidence = _evidence(domain, entity_id)
        retrieval = AsyncMock(spec=GovernedRetrievalService)
        retrieval.retrieve.return_value = (evidence,)
        service = LiaService(retrieval=retrieval)
        context = _context(CustomerPermission.READ, JobPermission.READ)
        continuation = LiaContext(
            domain=domain,
            entity_id=entity_id,
            authorization_version=context.authorization_version,
            topic_domains=(domain,),
        )
        for question in questions:
            response = await service.ask(
                AsyncMock(),
                context=context,
                request=LiaRequest(question=question, context=continuation),
            )
            assert response.subject_domain == domain
            assert response.subject_id == entity_id
            assert retrieval.retrieve.await_args.kwargs["entity_id"] == entity_id
            assert response.proposals == ()


@pytest.mark.asyncio
async def test_source_resolvers_apply_company_and_branch_scope() -> None:
    for resolver, argument in (
        (
            customer_lia_context_service.resolve_display_name,
            {"display_name": "Known Customer"},
        ),
        (job_lia_context_service.resolve_job_number, {"job_number": "306"}),
    ):
        result = MagicMock()
        result.all.return_value = [uuid4()]
        session = AsyncMock()
        session.scalars.return_value = result
        context = _context(CustomerPermission.READ, JobPermission.READ)
        await resolver(session, context=context, **argument)
        statement = session.scalars.await_args.args[0]
        rendered = str(statement)
        assert ".company_id" in rendered
        assert context.company.id in statement.compile().params.values()
        assert context.active_branch.id in {
            item
            for value in statement.compile().params.values()
            if isinstance(value, (list, tuple, set, frozenset))
            for item in value
        }

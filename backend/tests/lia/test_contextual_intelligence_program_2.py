from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.jobs.lia_context import CONTRACT_VERSION, JobLiaContextService
from app.jobs.repository import JobRepository
from app.lia.contracts import EvidenceReference
from app.lia.foundation import SOURCE_REGISTRY, SourceReadiness
from app.platform.permissions.codes import CustomerPermission, JobPermission
from tests.jobs.test_jobs_persistence import JobsFixture, build_job

pytest_plugins = ("tests.jobs.test_jobs_persistence",)


def _context(
    fixture: JobsFixture,
    *,
    company_id: UUID | None = None,
    branch_id: UUID | None = None,
    permissions: tuple[str, ...] = (CustomerPermission.READ, JobPermission.READ),
) -> SimpleNamespace:
    selected_branch = branch_id or fixture.branch_id
    return SimpleNamespace(
        company=SimpleNamespace(id=company_id or fixture.company_id),
        active_branch=SimpleNamespace(id=selected_branch),
        authorized_branch_ids=frozenset({selected_branch}),
        authorization_version=11,
        has_permission=lambda code: code in permissions,
    )


def test_context_contract_binds_scope_and_authorization() -> None:
    names = set(EvidenceReference.model_fields)
    assert {
        "source_contract_version",
        "company_id",
        "branch_ids",
        "authorization_version",
        "limitations",
    } <= names


def test_job_context_evolves_without_rewriting_accepted_foundation_registry() -> None:
    sources = {source.source_id: source for source in SOURCE_REGISTRY}
    assert sources["JOB_OPERATIONAL"].authority == "JOB_DOMAIN"
    assert sources["JOB_OPERATIONAL"].readiness is SourceReadiness.READY
    own_payroll = sources["PAYROLL_OWN_STATEMENT"]
    assert own_payroll.readiness is SourceReadiness.BLOCKED
    assert own_payroll.provenance_contract == "SERVER_RESOLVED_EMPLOYEE"


def test_program_contract_records_blocked_sources_and_non_authority() -> None:
    root = Path(__file__).resolve().parents[3]
    text = (
        root / "docs/architecture/lia/contextual-intelligence-program-2.md"
    ).read_text()
    for expected in (
        "LIA.CONTEXT.v1",
        "JOB.LIA_CONTEXT.v1",
        "SOURCE_REQUIRED",
        "AI_PROVIDER_NOT_CONFIGURED",
        "never accepts an Employee identity",
        "does not infer that a Payment receipt settles an Invoice",
        "hidden reasoning is never persisted",
    ):
        assert expected.casefold() in text.casefold()


def test_program_qualification_fingerprint_is_deterministic() -> None:
    root = Path(__file__).resolve().parents[3]
    payload = json.loads(
        (
            root
            / "docs/architecture/lia/contextual-intelligence-program-2-qualification.v1.json"
        ).read_text()
    )
    expected = payload.pop("qualification_fingerprint")
    actual = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert expected == actual


@pytest.mark.asyncio
async def test_job_projection_is_bounded_deterministic_and_excludes_free_text(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        job = await JobRepository.create_job(session, job=build_job(fixture))
    async with factory() as session:
        first = await JobLiaContextService().project(
            session, context=_context(fixture), job_id=job.id
        )
        second = await JobLiaContextService().project(
            session, context=_context(fixture), job_id=job.id
        )
    assert first is not None and second is not None
    assert first.contract_version == CONTRACT_VERSION
    assert first.evidence_digest == second.evidence_digest
    assert first.authorization_version == 11
    assert first.branch_id == fixture.branch_id
    assert "No hot water" not in first.model_dump_json()
    assert len(first.appointments) <= 10


@pytest.mark.asyncio
async def test_job_projection_fails_closed_before_foreign_or_unauthorized_retrieval(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> None:
    _, factory, fixture = jobs_database
    async with factory() as session, session.begin():
        job = await JobRepository.create_job(session, job=build_job(fixture))
    service = JobLiaContextService()
    async with factory() as session:
        assert (
            await service.project(
                session,
                context=_context(fixture, company_id=fixture.other_company_id),
                job_id=job.id,
            )
            is None
        )
        assert (
            await service.project(
                session,
                context=_context(fixture, branch_id=fixture.secondary_branch_id),
                job_id=job.id,
            )
            is None
        )
        assert (
            await service.project(
                session,
                context=_context(fixture, permissions=(CustomerPermission.READ,)),
                job_id=job.id,
            )
            is None
        )
        assert (
            await service.project(session, context=_context(fixture), job_id=uuid4())
            is None
        )

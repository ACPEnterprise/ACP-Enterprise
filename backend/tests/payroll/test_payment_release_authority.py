from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events.models import BusinessEvent
from app.payroll.contracts import (
    PayrollAuthorizationError,
    PayrollConflictError,
    canonical_digest,
)
from app.payroll.payment_release import (
    DestinationAdmissionState,
    DraftPaymentDestination,
    PaymentMethod,
    PaymentReleaseReviewDecision,
    PayrollPaymentReleaseService,
)
from app.payroll.permissions import PayrollPermission
from app.payroll.run_finalization import (
    PayrollRunDisposition,
    PayrollRunMemberInput,
    PayrollRunReviewDecision,
    PayrollRunService,
)
from app.payroll.tax_authority import ProtectedPayrollInputCipher
from app.platform.audit.models import AuditRecord
from tests.payroll.test_gross_pay_finalization import FakeContext
from tests.payroll.test_gross_pay_finalization import (
    finalization_database as _finalization_database_fixture,
)
from tests.payroll.test_payroll_run_finalization import (
    approved_tax_result,
    population,
)

finalization_database = _finalization_database_fixture
NOW = datetime(2026, 9, 10, 20, tzinfo=timezone.utc)


def payment_service() -> PayrollPaymentReleaseService:
    return PayrollPaymentReleaseService(
        cipher=ProtectedPayrollInputCipher(
            active_key_id="synthetic-key-v1", keys={"synthetic-key-v1": b"x" * 32}
        )
    )


async def approved_run(
    session: AsyncSession, values: dict[str, object]
):  # type: ignore[no-untyped-def]
    tax, _ = await approved_tax_result(session, values)
    company_id, employee_id = values["company_id"], values["employee_id"]
    assemble: Any = FakeContext(
        company_id, values["actor_id"], {PayrollPermission.RUN_ASSEMBLE}
    )
    review: Any = FakeContext(
        company_id, values["reviewer_id"], {PayrollPermission.RUN_REVIEW}
    )
    approve: Any = FakeContext(
        company_id, values["reviewer_id"], {PayrollPermission.RUN_APPROVE}
    )
    service = PayrollRunService()
    candidate = await service.assemble_candidate(
        session,
        context=assemble,
        population=population(company_id, tax.pay_period_id, (employee_id,)),
        member_inputs=(
            PayrollRunMemberInput(
                employee_id, PayrollRunDisposition.READY, tax_result_id=tax.id
            ),
        ),
        currency="USD",
        assembled_at=NOW,
    )
    run = await service.persist_candidate(session, context=assemble, candidate=candidate)
    await service.initiate_review(
        session, context=review, run_id=run.id, reason_code="synthetic"
    )
    await service.decide_review(
        session,
        context=review,
        run_id=run.id,
        decision=PayrollRunReviewDecision.ACCEPTED,
        reason_code="synthetic",
    )
    await service.approve(
        session, context=approve, run_id=run.id, reason_code="synthetic"
    )
    await session.refresh(run)
    return run, tax


def contexts(values: dict[str, object]) -> tuple[Any, Any, Any, Any]:
    manage = FakeContext(
        values["company_id"],
        values["actor_id"],
        {PayrollPermission.PAYMENT_INSTRUCTION_MANAGE},
    )
    assemble = FakeContext(
        values["company_id"],
        values["actor_id"],
        {PayrollPermission.PAYMENT_RELEASE_ASSEMBLE},
    )
    review = FakeContext(
        values["company_id"],
        values["reviewer_id"],
        {PayrollPermission.PAYMENT_RELEASE_REVIEW},
    )
    approve_read = FakeContext(
        values["company_id"],
        values["reviewer_id"],
        {
            PayrollPermission.PAYMENT_RELEASE_APPROVE,
            PayrollPermission.PAYMENT_RELEASE_READ,
        },
    )
    return manage, assemble, review, approve_read


async def destination(
    session: AsyncSession,
    service: PayrollPaymentReleaseService,
    context: Any,
    employee_id,  # type: ignore[no-untyped-def]
    *,
    method: PaymentMethod = PaymentMethod.DIRECT_DEPOSIT,
    version: int = 1,
):
    payload = (
        {"synthetic_routing": "TEST-ROUTING", "synthetic_account": "TEST-ACCOUNT"}
        if method is PaymentMethod.DIRECT_DEPOSIT
        else None
    )
    value = await service.create_destination(
        session,
        context=context,
        draft=DraftPaymentDestination(
            employee_id=employee_id,
            destination_version=version,
            method=method,
            destination_reference=f"protected-destination-{version}",
            masked_display="synthetic ending TEST",
            verification_evidence_digest=canonical_digest(
                {"synthetic-verification": version}
            ),
            effective_start=date(2026, 1, 1),
            effective_end=None,
            protected_payload=payload,
            audit_reason="Synthetic payment authority qualification",
        ),
    )
    return await service.approve_destination(
        session, context=context, destination_id=value.id
    )


@pytest.mark.asyncio
async def test_protected_destination_release_review_handoff_and_safe_events(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    service = payment_service()
    manage, assemble, review, approve_read = contexts(values)
    async with factory() as session:
        run, tax = await approved_run(session, values)
        await destination(session, service, manage, values["employee_id"])
        resolved = await service.resolve_destination(
            session,
            company_id=values["company_id"],
            employee_id=values["employee_id"],
            as_of_date=date(2026, 9, 4),
        )
        assert resolved.state is DestinationAdmissionState.READY
        candidate = await service.assemble_candidate(
            session,
            context=assemble,
            payroll_run_id=run.id,
            destinations={values["employee_id"]: resolved},
            assembled_at=NOW,
        )
        assert candidate.aggregate_release_amount == tax.net_pay_candidate
        first = await service.persist_candidate(
            session, context=assemble, candidate=candidate
        )
        replay = await service.persist_candidate(
            session, context=assemble, candidate=candidate
        )
        assert first.id == replay.id
        await service.initiate_review(
            session, context=review, release_id=first.id, reason_code="synthetic"
        )
        await service.decide_review(
            session,
            context=review,
            release_id=first.id,
            decision=PaymentReleaseReviewDecision.ACCEPTED,
            reason_code="synthetic",
        )
        await service.approve_release(
            session,
            context=approve_read,
            release_id=first.id,
            reason_code="synthetic",
        )
        handoff = await service.execution_handoff(
            session, context=approve_read, release_id=first.id
        )
        assert handoff.package_digest == first.package_digest
        events = tuple(
            (
                await session.scalars(
                    select(BusinessEvent).where(
                        BusinessEvent.entity_type.in_(
                            ("payroll_payment_destination", "payroll_payment_release")
                        )
                    )
                )
            ).all()
        )
        audits = tuple(
            (
                await session.scalars(
                    select(AuditRecord).where(
                        AuditRecord.resource_type.in_(
                            ("payroll_payment_destination", "payroll_payment_release")
                        )
                    )
                )
            ).all()
        )
        assert events and audits
        assert all("amount" not in str(item.payload) and "routing" not in str(item.payload) for item in events)
        assert all("amount" not in str(item.details) and "account" not in str(item.details) for item in audits)


@pytest.mark.asyncio
async def test_missing_unverified_paper_check_population_and_permissions(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    service = payment_service()
    manage, assemble, _, _ = contexts(values)
    async with factory() as session:
        run, _ = await approved_run(session, values)
        missing = await service.resolve_destination(session, company_id=values["company_id"], employee_id=values["employee_id"], as_of_date=date(2026, 9, 4))
        assert missing.state is DestinationAdmissionState.MISSING
        candidate = await service.assemble_candidate(session, context=assemble, payroll_run_id=run.id, destinations={values["employee_id"]: missing}, assembled_at=NOW)
        assert candidate.aggregate_release_amount == 0 and candidate.instructions[0].disposition.value == "blocked"
        with pytest.raises(PayrollConflictError, match="population"):
            await service.assemble_candidate(session, context=assemble, payroll_run_id=run.id, destinations={}, assembled_at=NOW)
        draft = await service.create_destination(session, context=manage, draft=DraftPaymentDestination(values["employee_id"], 1, PaymentMethod.PAPER_CHECK, "protected-check-destination", "synthetic paper check", canonical_digest({"paper": True}), date(2026, 1, 1), None, None, "Synthetic paper-check qualification"))
        unverified = await service.resolve_destination(session, company_id=values["company_id"], employee_id=values["employee_id"], as_of_date=date(2026, 9, 4))
        assert draft.lifecycle == "draft" and unverified.state is DestinationAdmissionState.UNVERIFIED
        await service.approve_destination(session, context=manage, destination_id=draft.id)
        paper = await service.resolve_destination(session, company_id=values["company_id"], employee_id=values["employee_id"], as_of_date=date(2026, 9, 4))
        assert paper.method is PaymentMethod.PAPER_CHECK
        no_permission = FakeContext(values["company_id"], values["actor_id"], set())
        with pytest.raises(PayrollAuthorizationError):
            await service.persist_candidate(session, context=no_permission, candidate=candidate)
        with pytest.raises(PayrollAuthorizationError):
            await service.initiate_review(session, context=assemble, release_id=uuid4(), reason_code="denied")


@pytest.mark.asyncio
async def test_changed_destination_supersession_and_cross_company_fail_closed(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    service = payment_service()
    manage, assemble, _, _ = contexts(values)
    async with factory() as session:
        run, _ = await approved_run(session, values)
        first_destination = await destination(session, service, manage, values["employee_id"])
        first_resolution = await service.resolve_destination(session, company_id=values["company_id"], employee_id=values["employee_id"], as_of_date=date(2026, 9, 4))
        first_candidate = await service.assemble_candidate(session, context=assemble, payroll_run_id=run.id, destinations={values["employee_id"]: first_resolution}, assembled_at=NOW)
        first = await service.persist_candidate(session, context=assemble, candidate=first_candidate)
        first_destination.lifecycle = "revoked"
        await session.commit()
        await destination(session, service, manage, values["employee_id"], version=2)
        changed = await service.resolve_destination(session, company_id=values["company_id"], employee_id=values["employee_id"], as_of_date=date(2026, 9, 4))
        second_candidate = await service.assemble_candidate(session, context=assemble, payroll_run_id=run.id, destinations={values["employee_id"]: changed}, assembled_at=NOW, supersedes_package_identity=first.package_identity)
        assert second_candidate.package_digest != first.package_digest
        second = await service.persist_candidate(session, context=assemble, candidate=second_candidate)
        await session.refresh(first)
        assert first.lifecycle == "superseded" and second.supersedes_release_id == first.id
        other = FakeContext(values["other_company_id"], values["actor_id"], {PayrollPermission.PAYMENT_RELEASE_ASSEMBLE})
        with pytest.raises(PayrollConflictError, match="approved Payroll run"):
            await service.assemble_candidate(session, context=other, payroll_run_id=run.id, destinations={values["employee_id"]: changed}, assembled_at=NOW)

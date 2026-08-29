from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select

from app.events.models import BusinessEvent
from app.payroll.contracts import PayrollAuthorizationError, PayrollConflictError
from app.payroll.finalization import PayrollGrossResultService
from app.payroll.models import (
    PayrollInputAuthorityVersion,
    PayrollProtectedInputEnvelope,
)
from app.payroll.permissions import PayrollPermission
from app.payroll.tax_authority import (
    AuthorityApplicability,
    AuthorityRequirement,
    DraftPayrollInputAuthority,
    PayrollInputAuthorityService,
    PayrollInputDomain,
    ProtectedPayrollInputCipher,
    TaxDeductionAdmissionState,
)
from app.platform.audit.models import AuditRecord
from tests.payroll.test_gross_pay_finalization import (
    FakeContext,
    candidate,
    finalization_database,  # noqa: F401
    seed_candidate_time,
)

pytestmark = pytest.mark.asyncio


def command(
    employee_id: UUID,
    *,
    domain: PayrollInputDomain = PayrollInputDomain.TAX,
    key: str = "federal_withholding_election",
    version: int = 1,
    start: date = date(2026, 8, 29),
    end: date | None = None,
    protected: bool = True,
    supersedes: UUID | None = None,
) -> DraftPayrollInputAuthority:
    return DraftPayrollInputAuthority(
        employee_id=employee_id,
        domain=domain,
        authority_key=key,
        authority_version=version,
        applicability=AuthorityApplicability.REQUIRED,
        effective_start=start,
        effective_end=end,
        jurisdiction_reference="synthetic-jurisdiction",
        calculation_basis="supplied_authority_reference",
        priority=1 if domain is PayrollInputDomain.DEDUCTION else None,
        public_parameters={"form_version": "synthetic-v1"},
        evidence_digest="a" * 64,
        audit_reason="Synthetic authority qualification",
        protected_payload=(
            {"synthetic_election": "confidential-fixture"} if protected else None
        ),
        supersedes_authority_id=supersedes,
    )


@pytest.fixture
def service() -> PayrollInputAuthorityService:
    return PayrollInputAuthorityService(
        cipher=ProtectedPayrollInputCipher(
            active_key_id="synthetic-key-v1", keys={"synthetic-key-v1": b"k" * 32}
        )
    )


async def test_protected_tax_authority_resolves_and_binds_gross_result(
    finalization_database,  # noqa: F811
    service: PayrollInputAuthorityService,  # type: ignore[no-untyped-def]
) -> None:
    factory, values = finalization_database
    employee_id: UUID = values["employee_id"]  # type: ignore[assignment]
    manage: Any = FakeContext(
        values["company_id"],
        values["actor_id"],
        {
            PayrollPermission.TAX_AUTHORITY_MANAGE,
            PayrollPermission.TAX_AUTHORITY_READ,
            PayrollPermission.CALCULATION_EXECUTE,
            PayrollPermission.CALCULATION_READ,
        },
    )
    approve: Any = FakeContext(
        values["company_id"],
        values["reviewer_id"],
        {PayrollPermission.TAX_AUTHORITY_APPROVE},
    )
    value = candidate(values)
    async with factory() as session:
        await seed_candidate_time(session, value, values["actor_id"])  # type: ignore[arg-type]
        gross = await PayrollGrossResultService().persist_candidate(
            session, context=manage, candidate=value
        )
        draft = await service.draft(
            session, context=manage, command=command(employee_id)
        )
        replay = await service.draft(
            session, context=manage, command=command(employee_id)
        )
        assert replay.id == draft.id
        assert (
            await service.read(session, context=manage, authority_id=draft.id)
        ).id == draft.id
        with pytest.raises(PayrollAuthorizationError):
            await service.read(
                session,
                context=FakeContext(
                    values["company_id"], values["actor_id"], set()
                ),
                authority_id=draft.id,
            )
        with pytest.raises(PayrollConflictError, match="contradicts"):
            await service.draft(
                session,
                context=manage,
                command=replace(command(employee_id), evidence_digest="b" * 64),
            )
        envelope = await session.get(
            PayrollProtectedInputEnvelope, draft.protected_envelope_id
        )
        assert envelope is not None
        assert b"confidential-fixture" not in envelope.ciphertext
        approved = await service.approve(
            session, context=approve, authority_id=draft.id
        )
        approved_replay = await service.draft(
            session, context=manage, command=command(employee_id)
        )
        assert approved_replay.id == approved.id
        result = await service.evaluate_admission(
            session,
            context=manage,
            gross_result_id=gross.id,
            as_of_date=date(2026, 9, 4),
            requirements=(
                AuthorityRequirement(
                    PayrollInputDomain.TAX,
                    "federal_withholding_election",
                    employee_id,
                ),
            ),
        )
        result.verify()
        assert result.state is TaxDeductionAdmissionState.READY
        assert result.gross_calculation_digest == gross.calculation_digest
        assert approved.authority_digest == result.resolutions[0].authority_digest
        audits = tuple((await session.scalars(select(AuditRecord))).all())
        events = tuple((await session.scalars(select(BusinessEvent))).all())
        serialized = repr([(item.details, item.action) for item in audits]) + repr(
            [(item.payload, item.event_type) for item in events]
        )
        assert "confidential-fixture" not in serialized


async def test_missing_expired_unapproved_and_not_applicable_admission(
    finalization_database,  # noqa: F811
    service: PayrollInputAuthorityService,  # type: ignore[no-untyped-def]
) -> None:
    factory, values = finalization_database
    employee_id: UUID = values["employee_id"]  # type: ignore[assignment]
    context: Any = FakeContext(
        values["company_id"],
        values["actor_id"],
        {
            PayrollPermission.TAX_AUTHORITY_MANAGE,
            PayrollPermission.DEDUCTION_AUTHORITY_MANAGE,
            PayrollPermission.CALCULATION_EXECUTE,
            PayrollPermission.CALCULATION_READ,
        },
    )
    reviewer: Any = FakeContext(
        values["company_id"],
        values["reviewer_id"],
        {
            PayrollPermission.TAX_AUTHORITY_APPROVE,
            PayrollPermission.DEDUCTION_AUTHORITY_APPROVE,
        },
    )
    value = candidate(values)
    async with factory() as session:
        await seed_candidate_time(session, value, values["actor_id"])  # type: ignore[arg-type]
        gross = await PayrollGrossResultService().persist_candidate(
            session, context=context, candidate=value
        )
        missing_requirement = AuthorityRequirement(
            PayrollInputDomain.TAX, "state_withholding", employee_id
        )
        missing = await service.evaluate_admission(
            session,
            context=context,
            gross_result_id=gross.id,
            as_of_date=date(2026, 9, 4),
            requirements=(missing_requirement,),
        )
        assert missing.state is TaxDeductionAdmissionState.MISSING
        expired_draft = await service.draft(
            session,
            context=context,
            command=command(
                employee_id,
                key="state_withholding",
                start=date(2026, 1, 1),
                end=date(2026, 2, 1),
            ),
        )
        await service.approve(
            session, context=reviewer, authority_id=expired_draft.id
        )
        expired = await service.evaluate_admission(
            session,
            context=context,
            gross_result_id=gross.id,
            as_of_date=date(2026, 9, 4),
            requirements=(missing_requirement,),
        )
        assert expired.state is TaxDeductionAdmissionState.EXPIRED
        await service.draft(
            session,
            context=context,
            command=command(employee_id, key="local_withholding"),
        )
        unapproved = await service.evaluate_admission(
            session,
            context=context,
            gross_result_id=gross.id,
            as_of_date=date(2026, 9, 4),
            requirements=(
                AuthorityRequirement(
                    PayrollInputDomain.TAX, "local_withholding", employee_id
                ),
            ),
        )
        assert unapproved.state is TaxDeductionAdmissionState.UNAPPROVED
        conflict_first = await service.draft(
            session,
            context=context,
            command=command(employee_id, key="fica_employee"),
        )
        await service.approve(
            session, context=reviewer, authority_id=conflict_first.id
        )
        conflict_second = await service.draft(
            session,
            context=context,
            command=command(employee_id, key="fica_employee", version=2),
        )
        conflict_second.lifecycle = "approved"
        conflict_second.approved_by_user_id = values["reviewer_id"]
        conflict_second.approved_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
        await session.commit()
        conflicting = await service.evaluate_admission(
            session,
            context=context,
            gross_result_id=gross.id,
            as_of_date=date(2026, 9, 4),
            requirements=(
                AuthorityRequirement(
                    PayrollInputDomain.TAX, "fica_employee", employee_id
                ),
            ),
        )
        assert conflicting.state is TaxDeductionAdmissionState.CONFLICTING
        not_applicable_command = command(
            employee_id,
            domain=PayrollInputDomain.DEDUCTION,
            key="synthetic_benefit",
            protected=False,
        )
        not_applicable_command = DraftPayrollInputAuthority(
            **{
                **not_applicable_command.__dict__,
                "applicability": AuthorityApplicability.NOT_APPLICABLE,
            }
        )
        draft = await service.draft(
            session, context=context, command=not_applicable_command
        )
        await service.approve(session, context=reviewer, authority_id=draft.id)
        result = await service.evaluate_admission(
            session,
            context=context,
            gross_result_id=gross.id,
            as_of_date=date(2026, 9, 4),
            requirements=(
                AuthorityRequirement(
                    PayrollInputDomain.DEDUCTION, "synthetic_benefit", employee_id
                ),
            ),
        )
        assert result.state is TaxDeductionAdmissionState.NOT_APPLICABLE


async def test_sod_permissions_company_isolation_and_supersession(
    finalization_database,  # noqa: F811
    service: PayrollInputAuthorityService,  # type: ignore[no-untyped-def]
) -> None:
    factory, values = finalization_database
    employee_id: UUID = values["employee_id"]  # type: ignore[assignment]
    manage: Any = FakeContext(
        values["company_id"],
        values["actor_id"],
        {
            PayrollPermission.DEDUCTION_AUTHORITY_MANAGE,
            PayrollPermission.DEDUCTION_AUTHORITY_APPROVE,
        },
    )
    approve: Any = FakeContext(
        values["company_id"],
        values["reviewer_id"],
        {PayrollPermission.DEDUCTION_AUTHORITY_APPROVE},
    )
    wrong_company: Any = FakeContext(
        values["other_company_id"],
        values["reviewer_id"],
        {PayrollPermission.DEDUCTION_AUTHORITY_APPROVE},
    )
    async with factory() as session:
        with pytest.raises(PayrollAuthorizationError):
            await service.draft(
                session,
                context=FakeContext(values["company_id"], values["actor_id"], set()),
                command=command(
                    employee_id,
                    domain=PayrollInputDomain.DEDUCTION,
                    key="retirement",
                ),
            )
        first = await service.draft(
            session,
            context=manage,
            command=command(
                employee_id,
                domain=PayrollInputDomain.DEDUCTION,
                key="retirement",
            ),
        )
        with pytest.raises(PayrollAuthorizationError, match="self-approve"):
            await service.approve(session, context=manage, authority_id=first.id)
        with pytest.raises(PayrollConflictError, match="outside Company"):
            await service.approve(
                session, context=wrong_company, authority_id=first.id
            )
        await service.approve(session, context=approve, authority_id=first.id)
        first_id = first.id
        overlapping = await service.draft(
            session,
            context=manage,
            command=command(
                employee_id,
                domain=PayrollInputDomain.DEDUCTION,
                key="retirement",
                version=2,
            ),
        )
        with pytest.raises(PayrollConflictError, match="overlap"):
            await service.approve(
                session, context=approve, authority_id=overlapping.id
            )
        await session.rollback()
        second = await service.draft(
            session,
            context=manage,
            command=command(
                employee_id,
                domain=PayrollInputDomain.DEDUCTION,
                key="retirement",
                version=3,
                start=date(2027, 1, 1),
                supersedes=first_id,
            ),
        )
        await service.approve(session, context=approve, authority_id=second.id)
        refreshed_first = await session.get(PayrollInputAuthorityVersion, first_id)
        assert refreshed_first is not None
        assert refreshed_first.lifecycle == "superseded"
        assert second.authority_digest != refreshed_first.authority_digest


async def test_public_parameters_reject_protected_identifiers(
    finalization_database,  # noqa: F811
    service: PayrollInputAuthorityService,  # type: ignore[no-untyped-def]
) -> None:
    factory, values = finalization_database
    context: Any = FakeContext(
        values["company_id"],
        values["actor_id"],
        {PayrollPermission.TAX_AUTHORITY_MANAGE},
    )
    unsafe = command(values["employee_id"], protected=False)  # type: ignore[arg-type]
    unsafe = DraftPayrollInputAuthority(
        **{**unsafe.__dict__, "public_parameters": {"tax_id": "synthetic"}}
    )
    async with factory() as session:
        with pytest.raises(Exception, match="protected input"):
            await service.draft(session, context=context, command=unsafe)

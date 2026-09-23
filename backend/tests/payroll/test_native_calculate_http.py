"""PostgreSQL-backed proof of first native Payroll calculation."""

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.database.session import get_database_session
from app.events.models import BusinessEvent
from app.payroll.contracts import CompensationType, canonical_digest
from app.payroll.models import (
    CompanyPayrollPolicyVersion,
    EmployeeCompensationAuthorityVersion,
    PayrollCalculationInputSnapshotRecord,
    PayrollGrossCalculationResultRecord,
    PayrollInputAuthorityVersion,
    PayrollProtectedInputEnvelope,
    PayrollRunMemberRecord,
    PayrollRunRecord,
    PayrollTaxDeductionResultRecord,
)
from app.payroll.operator_router import router
from app.payroll.permissions import PayrollPermission
from app.platform.audit.models import AuditRecord
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.idempotency.models import MutationReceipt
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.dependencies import get_authorization_context
from app.platform.permissions.models import Permission
from app.platform.users.models import User
from app.timekeeping.models import PayPeriod
from tests.payroll.test_gross_pay_calculation import (
    compensation as fixture_compensation,
)
from tests.payroll.test_gross_pay_calculation import (
    policy as fixture_policy,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def native_calculate_database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _protected_payload() -> dict[str, object]:
    return {
        "filing_status": "single",
        "step_2_checked": False,
        "step_3_credits": "0",
        "step_4a_other_income": "0",
        "step_4b_deductions": "0",
        "step_4c_extra_withholding": "0",
        "social_security_wages_ytd": "0",
        "medicare_wages_ytd": "0",
    }


async def _seed_case(factory: async_sessionmaker[AsyncSession]) -> tuple[UUID, UUID, str]:
    company_id, employee_id, actor_id, branch_id, period_id = (
        uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    )
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    start, end = date(2026, 9, 7), date(2026, 9, 13)
    async with factory() as session, session.begin():
        company = Company(
            id=company_id,
            name="Native Calculation Fixture",
            code=f"NC{uuid4().hex[:8].upper()}",
            status="active",
            timezone="America/New_York",
        )
        actor = User(
            id=actor_id,
            normalized_email=f"native-calc-{uuid4().hex}@example.invalid",
            first_name="Native",
            last_name="Calculator",
            display_name="Native Calculator",
            status="active",
            authorization_version=1,
        )
        branch = __import__("app.platform.branch.models", fromlist=["Branch"]).Branch(
            id=branch_id,
            company_id=company_id,
            name="Main",
            code=f"MAIN{uuid4().hex[:4].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        employee = Employee(
            id=employee_id,
            company_id=company_id,
            home_branch_id=branch_id,
            employee_number=f"NATIVE-{uuid4().hex[:8]}",
            first_name="Test",
            last_name="Employee",
            display_name="Test Employee",
            employee_type="employee",
            status="active",
        )
        membership = Membership(
            user_id=actor_id,
            company_id=company_id,
            status="active",
            default_branch_id=branch_id,
            has_all_branch_access=True,
        )
        period = PayPeriod(
            id=period_id,
            company_id=company_id,
            period_start=start,
            period_end=end,
            processing_date=date(2026, 9, 14),
            payday=date(2026, 9, 15),
            timezone="America/New_York",
            schedule_definition_id="weekly",
            schedule_version=1,
            created_by_user_id=actor_id,
        )
        session.add_all([company, actor, branch, employee, membership, period])
        await session.flush()

        policy_value = fixture_policy(company_id)
        policy_value = replace(
            policy_value,
            approved_by_user_id=actor_id,
            approved_at=now,
            authority_digest="",
        )
        policy_value = replace(policy_value, authority_digest=canonical_digest(policy_value.canonical_content()))
        policy = CompanyPayrollPolicyVersion(
            id=policy_value.policy_id,
            company_id=company_id,
            policy_version=policy_value.policy_version,
            effective_start=policy_value.effective_start,
            effective_end=policy_value.effective_end,
            lifecycle="approved",
            definition_version="payroll.company-policy.v1",
            definition=policy_value.definition.canonical_content(),
            decision_evidence_digest=policy_value.decision_evidence_digest,
            authority_digest=policy_value.authority_digest,
            drafted_by_user_id=actor_id,
            approved_by_user_id=actor_id,
            approved_at=now,
            audit_reason="isolated first-calculation fixture",
        )
        compensation_value = fixture_compensation(
            company_id, employee_id, kind=CompensationType.SALARIED, rate=Decimal("1000.00")
        )
        compensation_value = replace(
            compensation_value,
            approved_by_user_id=actor_id,
            approved_at=now,
            authority_digest="",
        )
        compensation_value = replace(compensation_value, authority_digest=canonical_digest(compensation_value.canonical_content()))
        compensation = EmployeeCompensationAuthorityVersion(
            id=compensation_value.authority_id,
            company_id=company_id,
            employee_id=employee_id,
            authority_version=compensation_value.authority_version,
            effective_start=compensation_value.effective_start,
            effective_end=compensation_value.effective_end,
            lifecycle="approved",
            definition_version="payroll.compensation-authority.v1",
            compensation_type="salaried",
            hourly_rate=None,
            salary_amount=Decimal("1000.00"),
            salary_frequency="weekly",
            worker_class_reference=compensation_value.worker_class_reference,
            additional_earning_types=[],
            recurring_components=[],
            decision_evidence_digest=compensation_value.decision_evidence_digest,
            authority_digest=compensation_value.authority_digest,
            drafted_by_user_id=actor_id,
            approved_by_user_id=compensation_value.approved_by_user_id,
            approved_at=compensation_value.approved_at,
            audit_reason="isolated first-calculation fixture",
        )
        session.add_all([policy, compensation])
        cipher_key = b"n" * 32
        payload = _protected_payload()
        encrypted = AESGCM(cipher_key)
        nonce = b"0123456789ab"
        import json

        ciphertext = encrypted.encrypt(nonce, json.dumps(payload).encode(), str(company_id).encode())
        envelope_id = uuid4()
        session.add(
            PayrollProtectedInputEnvelope(
                id=envelope_id,
                company_id=company_id,
                key_id="native-test",
                nonce=nonce,
                ciphertext=ciphertext,
                content_digest=canonical_digest(payload),
                created_by_user_id=actor_id,
            )
        )
        await session.flush()
        for key in ("federal_income_tax", "social_security_employee", "medicare_employee"):
            session.add(
                PayrollInputAuthorityVersion(
                    company_id=company_id,
                    employee_id=employee_id,
                    authority_domain="tax",
                    authority_key=key,
                    authority_version=1,
                    definition_version="payroll.tax-deduction-authority.v1",
                    applicability="required",
                    effective_start=start,
                    lifecycle="approved",
                    jurisdiction_reference="US-FL",
                    calculation_basis="fixture",
                    priority=None,
                    public_parameters={},
                    evidence_digest="e" * 64,
                    authority_digest=canonical_digest({"key": key, "version": 1}),
                    protected_envelope_id=envelope_id,
                    drafted_by_user_id=actor_id,
                    approved_by_user_id=actor_id,
                    approved_at=now,
                    audit_reason="isolated first-calculation fixture",
                )
            )
        await session.flush()
        run_digest = canonical_digest({"company_id": str(company_id), "period": str(period_id), "employee": str(employee_id)})
        run = PayrollRunRecord(
            company_id=company_id,
            pay_period_id=period_id,
            schedule_definition_id="weekly",
            schedule_version="1",
            assembly_version="payroll.run.v1",
            population_identity="native-http-fixture",
            population_digest=canonical_digest({"employee": str(employee_id)}),
            currency="USD",
            run_identity=f"native-http:{run_digest}",
            run_digest=run_digest,
            aggregate_gross=Decimal(0),
            aggregate_employee_taxes=Decimal(0),
            aggregate_employee_deductions=Decimal(0),
            aggregate_net_pay=Decimal(0),
            aggregate_employer_contributions=Decimal(0),
            assembled_by_user_id=actor_id,
            assembled_at=now,
            lifecycle="assembled",
            review_state="not_started",
        )
        session.add(run)
        await session.flush()
        session.add(
            PayrollRunMemberRecord(
                company_id=company_id,
                run_id=run.id,
                employee_id=employee_id,
                disposition="pending_calculation",
                membership_digest=canonical_digest({"employee": str(employee_id)}),
                blocker_codes=[],
            )
        )
    return company_id, run.id, run_digest


async def test_first_calculation_http_persists_new_authority(
    native_calculate_database: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    company_id, run_id, run_digest = await _seed_case(native_calculate_database)
    monkeypatch.setattr(settings, "payroll_input_active_kid", "native-test")
    monkeypatch.setattr(settings, "payroll_input_encryption_keys", {"native-test": "bm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm5ubm4="})

    async with native_calculate_database() as session:
        member = await session.scalar(select(PayrollRunMemberRecord).where(PayrollRunMemberRecord.run_id == run_id))
        assert member is not None
        assert member.gross_result_id is None and member.tax_result_id is None
        assert await session.scalar(select(PayrollGrossCalculationResultRecord.id).where(PayrollGrossCalculationResultRecord.pay_period_id == member.run_id)) is None

        company = await session.get(Company, company_id)
        actor = await session.scalar(select(User).join(Membership, Membership.user_id == User.id).where(Membership.company_id == company_id))
        membership = await session.scalar(select(Membership).where(Membership.company_id == company_id))
        permissions = list((await session.scalars(select(Permission))).all())
        required_permissions = {
            PayrollPermission.CALCULATION_EXECUTE,
            PayrollPermission.CALCULATION_READ,
            PayrollPermission.CALCULATION_REVIEW,
            PayrollPermission.ADMISSION_REVIEW,
            PayrollPermission.TAX_CALCULATION_EXECUTE,
            PayrollPermission.TAX_AUTHORITY_READ,
            PayrollPermission.TAX_RESULT_READ,
        }
        known = {item.code for item in permissions}
        for code in sorted(required_permissions - known):
            value = Permission(
                code=code,
                name=code,
                description="isolated Payroll qualification permission",
                resource="payroll",
                action=code.lower(),
                status="active",
            )
            session.add(value)
            permissions.append(value)
        await session.flush()
        assert company is not None and actor is not None and membership is not None
        assert await session.scalar(select(CompanyPayrollPolicyVersion).where(CompanyPayrollPolicyVersion.company_id == company_id)) is not None
        assert await session.scalar(select(EmployeeCompensationAuthorityVersion).where(EmployeeCompensationAuthorityVersion.company_id == company_id, EmployeeCompensationAuthorityVersion.employee_id == member.employee_id)) is not None
        context = AuthorizationContext(user=actor, company=company, membership=membership, authorized_branches=(), active_branch=None, effective_roles=(), effective_permissions=tuple(permissions), credential_version=1, authorization_version=1)

    app = FastAPI()
    app.include_router(router)

    async def db_override() -> AsyncIterator[AsyncSession]:
        async with native_calculate_database() as session:
            yield session

    async def context_override() -> AuthorizationContext:
        return context

    app.dependency_overrides[get_database_session] = db_override
    app.dependency_overrides[get_authorization_context] = context_override
    payload = {"idempotency_key": "native-first-calculate", "expected_run_digest": run_digest}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/v1/payroll/operator/runs/{run_id}/calculate", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "calculated"
    async with native_calculate_database() as session:
        member = await session.scalar(select(PayrollRunMemberRecord).where(PayrollRunMemberRecord.run_id == run_id))
        assert member is not None and member.gross_result_id is not None and member.tax_result_id is not None
        assert await session.scalar(select(PayrollCalculationInputSnapshotRecord).where(PayrollCalculationInputSnapshotRecord.run_id == run_id)) is not None
        assert await session.scalar(select(MutationReceipt).where(MutationReceipt.idempotency_key == "native-first-calculate")) is not None
        assert await session.scalar(select(AuditRecord).where(AuditRecord.resource_id == run_id)) is not None
        assert await session.scalar(select(BusinessEvent).where(BusinessEvent.entity_id == run_id)) is not None
        tax = await session.get(PayrollTaxDeductionResultRecord, member.tax_result_id)
        assert tax is not None and tax.net_pay_candidate > 0
        replay = await session.scalar(select(MutationReceipt).where(MutationReceipt.idempotency_key == "native-first-calculate"))
        assert replay is not None and replay.result_id == run_id

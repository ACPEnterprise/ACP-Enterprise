from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.workforce.employee_administration import (
    MOBILE_REQUIRED_PERMISSION_CODES,
    EmployeeAdministrationService,
)
from app.workforce.records import (
    WorkforceBranchEligibilityRecord,
    WorkforceCapabilityProfileRecord,
    WorkforceCapabilityRecord,
    WorkforceCertificationRecord,
    WorkforceLanguageRecord,
)
from app.workforce.schemas import WorkforceEmployeeDetail
from app.workforce.service import WorkforceOperationsService


def profile(*, certification_status: str = "active", expires_on: date | None = None):
    now = datetime.now(timezone.utc)
    return WorkforceCapabilityProfileRecord(
        id=uuid4(),
        company_id=uuid4(),
        employee_id=uuid4(),
        status="active",
        concurrency_version=1,
        created_at=now,
        updated_at=now,
        capabilities=(
            WorkforceCapabilityRecord(
                uuid4(), "technician", "Technician", "qualified", "active"
            ),
        ),
        certifications=(
            WorkforceCertificationRecord(
                uuid4(),
                "trade",
                "Trade credential",
                "SAFE-REF",
                certification_status,
                now.date(),
                expires_on,
            ),
        ),
        branch_eligibilities=(
            WorkforceBranchEligibilityRecord(uuid4(), "active", None, None),
        ),
        languages=(
            WorkforceLanguageRecord(
                uuid4(),
                "es",
                "Spanish",
                "Español",
                "professional",
                None,
                None,
                True,
                False,
                "active",
            ),
        ),
    )


def employee(*, status: str = "active"):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        status=status, archived_at=None, home_branch_id=uuid4(), updated_at=now
    )


def test_readiness_uses_explicit_capability_credential_and_branch_evidence() -> None:
    state, blockers = WorkforceOperationsService._readiness(employee(), profile())
    assert state == "READY"
    assert blockers == ()


def test_expired_credential_is_an_explicit_blocker() -> None:
    state, blockers = WorkforceOperationsService._readiness(
        employee(), profile(expires_on=date(2020, 1, 1))
    )
    assert state == "BLOCKED"
    assert blockers == ("credential_not_current",)


def test_missing_profile_remains_visible_as_insufficient_evidence() -> None:
    state, blockers = WorkforceOperationsService._readiness(employee(), None)
    assert state == "INSUFFICIENT_EVIDENCE"
    assert blockers == ("capability_profile_missing",)


def test_public_workforce_contract_cannot_expose_payroll_material() -> None:
    forbidden = {"compensation", "tax", "deduction", "bank", "net_pay", "pay_rate"}
    assert not forbidden.intersection(WorkforceEmployeeDetail.model_fields)
    assert "availability" in WorkforceEmployeeDetail.model_fields


def test_mobile_readiness_uses_effective_permissions_not_role_names() -> None:
    access, mobile, blockers = EmployeeAdministrationService._access_and_mobile_readiness(
        employee_status="active",
        membership_status="active",
        user_status="active",
        has_branch_access=True,
        effective_permission_codes=MOBILE_REQUIRED_PERMISSION_CODES,
    )
    assert (access, mobile, blockers) == ("ACTIVE", "READY", ())

    missing = MOBILE_REQUIRED_PERMISSION_CODES - {"COMPANY_JOB_EXECUTE"}
    access, mobile, blockers = EmployeeAdministrationService._access_and_mobile_readiness(
        employee_status="active",
        membership_status="active",
        user_status="active",
        has_branch_access=True,
        effective_permission_codes=missing,
    )
    assert access == "ACTIVE"
    assert mobile == "BLOCKED"
    assert blockers == ("mobile_permissions_missing",)


def test_employee_access_status_distinguishes_invited_and_disabled() -> None:
    invited = EmployeeAdministrationService._access_and_mobile_readiness(
        employee_status="active",
        membership_status="invited",
        user_status="invited",
        has_branch_access=True,
        effective_permission_codes=frozenset(),
    )
    assert invited[0] == "INVITED"
    disabled = EmployeeAdministrationService._access_and_mobile_readiness(
        employee_status="inactive",
        membership_status="active",
        user_status="active",
        has_branch_access=True,
        effective_permission_codes=MOBILE_REQUIRED_PERMISSION_CODES,
    )
    assert disabled[0] == "DISABLED"
    assert "employee_inactive" in disabled[2]

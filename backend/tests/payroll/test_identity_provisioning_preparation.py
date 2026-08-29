import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.payroll.company_policy_configurations.all_county_v1 import (
    build_all_county_payroll_policy_v1,
)
from app.payroll.contracts import PayrollAdmissionState, evaluate_payroll_admission
from app.payroll.identity_provisioning.all_county_v1 import (
    BASE_TIMEKEEPING,
    EMPLOYEES,
    SUPERVISOR_TIMEKEEPING_ADDITIONAL,
    LoginAuthority,
    ProvisioningLifecycle,
    ProvisioningManifestError,
    build_all_county_identity_provisioning_v1,
)
from app.timekeeping.permissions import TimekeepingPermission


def manifest():
    return build_all_county_identity_provisioning_v1(
        company_id=uuid4(),
        main_branch_id=uuid4(),
        michael_existing_user_id=uuid4(),
    )


def test_manifest_is_deterministic_safe_and_represents_all_eight() -> None:
    company_id, branch_id, michael_user_id = uuid4(), uuid4(), uuid4()
    first = build_all_county_identity_provisioning_v1(
        company_id=company_id,
        main_branch_id=branch_id,
        michael_existing_user_id=michael_user_id,
    )
    replay = build_all_county_identity_provisioning_v1(
        company_id=company_id,
        main_branch_id=branch_id,
        michael_existing_user_id=michael_user_id,
    )
    assert len(first.employees) == 8
    assert first.manifest_digest == replay.manifest_digest
    assert {employee.display_name for employee in first.employees} == {
        "Michael Fouse", "Lianne Hernandez", "Alex Donahue", "Melvin Santiago",
        "Adam Mari", "Dareis Montgomery", "Dakota Wilcox", "Jason Calci",
    }
    serialized = json.dumps(
        [employee.canonical_content() for employee in first.employees], sort_keys=True
    )
    assert "@" not in serialized and "email" not in serialized.lower()
    assert "compensation_input_required" in serialized
    assert all(employee.home_branch_code == "MAIN" for employee in first.employees)


def test_michael_reuses_existing_user_and_seven_require_protected_input() -> None:
    value = manifest()
    michael = value.employee("michael-fouse")
    assert michael.login_authority is LoginAuthority.EXISTING_VERIFIED_USER
    assert sum(
        employee.login_authority is LoginAuthority.PROTECTED_LOGIN_INPUT_REQUIRED
        for employee in value.employees
    ) == 7
    role_id = uuid4()
    command = value.prepare_onboarding_command(
        employee_key="michael-fouse",
        request_key="michael-v1",
        role_ids={BASE_TIMEKEEPING.profile_id: role_id},
    )
    assert command.existing_user_id == value.michael_existing_user_id
    assert command.login_email is None and command.branch_id == value.main_branch_id
    with pytest.raises(ProvisioningManifestError, match="Existing identity"):
        value.prepare_onboarding_command(
            employee_key="michael-fouse",
            request_key="invalid",
            role_ids={BASE_TIMEKEEPING.profile_id: role_id},
            protected_login=SecretStr("must-not-be-used@example.test"),
        )


def test_protected_login_and_role_composition_fail_closed() -> None:
    value = manifest()
    with pytest.raises(ProvisioningManifestError, match="Protected login"):
        value.prepare_onboarding_command(
            employee_key="lianne-hernandez",
            request_key="lianne-v1",
            role_ids={BASE_TIMEKEEPING.profile_id: uuid4()},
        )
    protected = SecretStr("synthetic.employee@example.test")
    command = value.prepare_onboarding_command(
        employee_key="lianne-hernandez",
        request_key="lianne-v1",
        role_ids={BASE_TIMEKEEPING.profile_id: uuid4()},
        protected_login=protected,
    )
    assert command.login_email == protected.get_secret_value()
    assert protected.get_secret_value() not in repr(protected)
    assert protected.get_secret_value() not in repr(command)
    with pytest.raises(ProvisioningManifestError, match="role composition"):
        value.prepare_onboarding_command(
            employee_key="alex-donahue",
            request_key="alex-v1",
            role_ids={BASE_TIMEKEEPING.profile_id: uuid4()},
            protected_login=protected,
        )


def test_timekeeping_roles_are_narrow_and_alex_alone_gets_supervisor_profile() -> None:
    assert set(BASE_TIMEKEEPING.permission_codes) == {
        TimekeepingPermission.OWN_PUNCH, TimekeepingPermission.OWN_READ,
    }
    assert set(SUPERVISOR_TIMEKEEPING_ADDITIONAL.permission_codes) == {
        TimekeepingPermission.MANUAL_ENTRY, TimekeepingPermission.CORRECT,
        TimekeepingPermission.APPROVE, TimekeepingPermission.ADMIN_READ,
    }
    assert all(
        code.startswith("COMPANY_TIMEKEEPING_")
        for code in (*BASE_TIMEKEEPING.permission_codes, *SUPERVISOR_TIMEKEEPING_ADDITIONAL.permission_codes)
    )
    elevated = [
        employee.employee_key for employee in EMPLOYEES
        if SUPERVISOR_TIMEKEEPING_ADDITIONAL.profile_id in employee.role_profile_ids
    ]
    assert elevated == ["alex-donahue"]


def test_allocator_preview_is_non_authoritative_unique_shape() -> None:
    preview = manifest().preview_employee_number_shape(next_value=1)
    assert preview == tuple(f"EMP-{index:04d}" for index in range(1, 9))
    assert len(preview) == len(set(preview)) == 8


def test_activation_and_payroll_progression_remain_fail_closed() -> None:
    assert tuple(ProvisioningLifecycle) == (
        ProvisioningLifecycle.PROVISIONING_REQUIRED,
        ProvisioningLifecycle.IDENTITY_PROVISIONED,
        ProvisioningLifecycle.INVITATION_PENDING,
        ProvisioningLifecycle.ACTIVATED,
        ProvisioningLifecycle.WORKDAY_READY,
    )
    company_id = uuid4()
    policy_bundle = build_all_county_payroll_policy_v1(
        company_id=company_id,
        approver_user_id=uuid4(),
        approved_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
    )
    policy = policy_bundle.policy
    blocked_identity = evaluate_payroll_admission(
        company_id=company_id,
        identity_resolved=False,
        policy=policy,
        compensation=None,
        time_input=None,
        pay_period_schedule_definition_id=(
            policy_bundle.first_period.schedule_definition_id
        ),
        pay_period_schedule_version=policy_bundle.first_period.schedule_version,
    )
    identity_satisfied = evaluate_payroll_admission(
        company_id=company_id,
        identity_resolved=True,
        policy=policy,
        compensation=None,
        time_input=None,
        pay_period_schedule_definition_id=(
            policy_bundle.first_period.schedule_definition_id
        ),
        pay_period_schedule_version=policy_bundle.first_period.schedule_version,
    )
    assert blocked_identity.state is PayrollAdmissionState.BLOCKED_IDENTITY
    assert identity_satisfied.state is PayrollAdmissionState.BLOCKED_COMPENSATION


def test_safe_runbook_requires_protected_execution_without_values() -> None:
    steps = manifest().safe_activation_runbook()
    assert len(steps) == 10
    rendered = " ".join(steps).lower()
    assert "protected runtime input" in rendered
    assert "displaying its secret" in rendered
    assert "@" not in rendered

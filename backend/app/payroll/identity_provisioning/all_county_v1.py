"""Non-sensitive All County identity provisioning manifest v1.

Building this manifest never creates an identity, allocates a number, issues an
invitation, grants a role, or activates a credential.
"""

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from uuid import UUID

from pydantic import SecretStr

from app.platform.onboarding.service import OnboardingCommand
from app.timekeeping.permissions import TimekeepingPermission

CONFIGURATION_ID: Final = "all-county.identity-provisioning.v1"
COMPANY_REFERENCE: Final = "all-county-plumbing-and-leak"
MANIFEST_VERSION: Final = 1
HOME_BRANCH_CODE: Final = "MAIN"
EMPLOYEE_NUMBER_PREFIX: Final = "EMP-"
EMPLOYEE_NUMBER_WIDTH: Final = 4


class ProvisioningManifestError(ValueError):
    pass


class LoginAuthority(StrEnum):
    EXISTING_VERIFIED_USER = "existing_verified_user"
    PROTECTED_LOGIN_INPUT_REQUIRED = "protected_login_input_required"


class ProvisioningLifecycle(StrEnum):
    PROVISIONING_REQUIRED = "provisioning_required"
    IDENTITY_PROVISIONED = "identity_provisioned"
    INVITATION_PENDING = "invitation_pending"
    ACTIVATED = "activated"
    WORKDAY_READY = "workday_ready"


@dataclass(frozen=True)
class TimekeepingRoleProfile:
    profile_id: str
    permission_codes: tuple[str, ...]

    def validate(self) -> None:
        if not self.permission_codes or len(set(self.permission_codes)) != len(
            self.permission_codes
        ):
            raise ProvisioningManifestError("Timekeeping role profile is invalid.")
        if any(code not in TimekeepingPermission.ALL for code in self.permission_codes):
            raise ProvisioningManifestError("Role profile exceeds Timekeeping authority.")


BASE_TIMEKEEPING = TimekeepingRoleProfile(
    "all-county.timekeeping-base.v1",
    (TimekeepingPermission.OWN_PUNCH, TimekeepingPermission.OWN_READ),
)
SUPERVISOR_TIMEKEEPING_ADDITIONAL = TimekeepingRoleProfile(
    "all-county.timekeeping-supervisor-additional.v1",
    (
        TimekeepingPermission.MANUAL_ENTRY,
        TimekeepingPermission.CORRECT,
        TimekeepingPermission.APPROVE,
        TimekeepingPermission.ADMIN_READ,
    ),
)


@dataclass(frozen=True)
class EmployeeProvisioningSpec:
    employee_key: str
    display_name: str
    first_name: str
    last_name: str
    pay_type: str
    worker_class: str
    home_branch_code: str
    login_authority: LoginAuthority
    role_profile_ids: tuple[str, ...]
    phone_login_intended: bool = True
    compensation_state: str = "compensation_input_required"

    def canonical_content(self) -> dict[str, object]:
        return {
            "employee_key": self.employee_key,
            "display_name": self.display_name,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "pay_type": self.pay_type,
            "worker_class": self.worker_class,
            "home_branch_code": self.home_branch_code,
            "login_authority": self.login_authority.value,
            "role_profile_ids": self.role_profile_ids,
            "phone_login_intended": self.phone_login_intended,
            "compensation_state": self.compensation_state,
        }


@dataclass(frozen=True)
class AllCountyIdentityProvisioningV1:
    company_reference: str
    company_id: UUID
    main_branch_id: UUID
    michael_existing_user_id: UUID
    configuration_id: str
    manifest_version: int
    employee_number_prefix: str
    employee_number_width: int
    role_profiles: tuple[TimekeepingRoleProfile, ...]
    employees: tuple[EmployeeProvisioningSpec, ...]
    manifest_digest: str

    def employee(self, employee_key: str) -> EmployeeProvisioningSpec:
        matches = [item for item in self.employees if item.employee_key == employee_key]
        if len(matches) != 1:
            raise ProvisioningManifestError("Provisioning subject is unavailable.")
        return matches[0]

    def role_profile(self, profile_id: str) -> TimekeepingRoleProfile:
        matches = [item for item in self.role_profiles if item.profile_id == profile_id]
        if len(matches) != 1:
            raise ProvisioningManifestError("Provisioning role profile is unavailable.")
        return matches[0]

    def prepare_onboarding_command(
        self,
        *,
        employee_key: str,
        request_key: str,
        role_ids: dict[str, UUID],
        protected_login: SecretStr | None = None,
    ) -> OnboardingCommand:
        employee = self.employee(employee_key)
        expected_profiles = set(employee.role_profile_ids)
        if set(role_ids) != expected_profiles:
            raise ProvisioningManifestError("Approved role composition is incomplete.")
        if employee.login_authority is LoginAuthority.EXISTING_VERIFIED_USER:
            if protected_login is not None:
                raise ProvisioningManifestError("Existing identity cannot be replaced.")
            login_email = None
            existing_user_id = self.michael_existing_user_id
        else:
            if protected_login is None or not protected_login.get_secret_value().strip():
                raise ProvisioningManifestError("Protected login input is required.")
            login_email = protected_login.get_secret_value()
            existing_user_id = None
        return OnboardingCommand(
            request_key=request_key,
            branch_id=self.main_branch_id,
            first_name=employee.first_name,
            last_name=employee.last_name,
            display_name=employee.display_name,
            employee_type="employee",
            employee_number_prefix=self.employee_number_prefix,
            employee_number_width=self.employee_number_width,
            role_ids=tuple(role_ids[profile] for profile in employee.role_profile_ids),
            login_email=login_email,
            existing_user_id=existing_user_id,
        )

    def preview_employee_number_shape(self, *, next_value: int = 1) -> tuple[str, ...]:
        if next_value < 1:
            raise ProvisioningManifestError("Employee-number preview is invalid.")
        return tuple(
            f"{self.employee_number_prefix}{value:0{self.employee_number_width}d}"
            for value in range(next_value, next_value + len(self.employees))
        )

    def safe_activation_runbook(self) -> tuple[str, ...]:
        return (
            "Revalidate the authoritative Company and MAIN Branch.",
            "Select one manifest Employee; do not name-match an existing identity.",
            "For Michael, select the verified existing-User reuse operation.",
            "For another Employee, enter the login identity through protected runtime input.",
            "Submit one idempotent onboarding request with the approved role profiles.",
            "Verify the safe invitation delivery lifecycle without displaying its secret.",
            "Have the intended recipient establish their credential directly.",
            "Verify User, Membership, Employee, Company, and MAIN Branch linkage.",
            "Verify only the manifest Timekeeping permissions.",
            "Verify Workday self-resolution and Payroll identity admission.",
        )


def _employee(
    employee_key: str,
    display_name: str,
    pay_type: str,
    worker_class: str,
    *,
    existing: bool = False,
    supervisor: bool = False,
) -> EmployeeProvisioningSpec:
    first_name, last_name = display_name.split(" ", 1)
    profiles = [BASE_TIMEKEEPING.profile_id]
    if supervisor:
        profiles.append(SUPERVISOR_TIMEKEEPING_ADDITIONAL.profile_id)
    return EmployeeProvisioningSpec(
        employee_key,
        display_name,
        first_name,
        last_name,
        pay_type,
        worker_class,
        HOME_BRANCH_CODE,
        (
            LoginAuthority.EXISTING_VERIFIED_USER
            if existing
            else LoginAuthority.PROTECTED_LOGIN_INPUT_REQUIRED
        ),
        tuple(profiles),
    )


EMPLOYEES: Final = (
    _employee("michael-fouse", "Michael Fouse", "salaried", "owner_salaried_management", existing=True),
    _employee("lianne-hernandez", "Lianne Hernandez", "salaried", "salaried_office_management"),
    _employee("alex-donahue", "Alex Donahue", "hourly", "hourly_supervisor", supervisor=True),
    _employee("melvin-santiago", "Melvin Santiago", "hourly", "hourly_labor"),
    _employee("adam-mari", "Adam Mari", "hourly", "hourly_labor"),
    _employee("dareis-montgomery", "Dareis Montgomery", "hourly", "hourly_labor"),
    _employee("dakota-wilcox", "Dakota Wilcox", "hourly", "hourly_labor"),
    _employee("jason-calci", "Jason Calci", "hourly", "hourly_labor"),
)


def build_all_county_identity_provisioning_v1(
    *, company_id: UUID, main_branch_id: UUID, michael_existing_user_id: UUID
) -> AllCountyIdentityProvisioningV1:
    profiles = (BASE_TIMEKEEPING, SUPERVISOR_TIMEKEEPING_ADDITIONAL)
    for profile in profiles:
        profile.validate()
    canonical: dict[str, object] = {
        "configuration_id": CONFIGURATION_ID,
        "manifest_version": MANIFEST_VERSION,
        "company_reference": COMPANY_REFERENCE,
        "company_id": str(company_id),
        "main_branch_id": str(main_branch_id),
        "michael_existing_user_id": str(michael_existing_user_id),
        "employee_number": {
            "prefix": EMPLOYEE_NUMBER_PREFIX,
            "width": EMPLOYEE_NUMBER_WIDTH,
            "reuse": "prohibited",
        },
        "role_profiles": tuple(
            {
                "profile_id": profile.profile_id,
                "permission_codes": profile.permission_codes,
            }
            for profile in profiles
        ),
        "employees": tuple(employee.canonical_content() for employee in EMPLOYEES),
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return AllCountyIdentityProvisioningV1(
        COMPANY_REFERENCE,
        company_id,
        main_branch_id,
        michael_existing_user_id,
        CONFIGURATION_ID,
        MANIFEST_VERSION,
        EMPLOYEE_NUMBER_PREFIX,
        EMPLOYEE_NUMBER_WIDTH,
        profiles,
        EMPLOYEES,
        digest,
    )

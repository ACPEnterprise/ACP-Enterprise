from dataclasses import dataclass
from enum import StrEnum


class RealRosterRole(StrEnum):
    ADMIN = "ADMIN"
    OFFICE_MANAGER = "OFFICE_MANAGER"
    OFFICE_STAFF = "OFFICE_STAFF"
    FIELD_MANAGER = "FIELD_MANAGER"
    FIELD_TECH = "FIELD_TECH"
    HELPER = "HELPER"


class RealRosterAdmission(StrEnum):
    SAFE_CREATE = "SAFE_CREATE"
    ALREADY_ACTIVE = "ALREADY_ACTIVE"
    OWNER_IDENTITY_DECISION_REQUIRED = "OWNER_IDENTITY_DECISION_REQUIRED"
    HISTORICAL_TERMINATED = "HISTORICAL_TERMINATED"


@dataclass(frozen=True, slots=True)
class RealRosterPerson:
    key: str
    display_name: str
    role: RealRosterRole
    source_employee_id: str | None
    source_login_email: str | None
    owner_login_email: str | None
    admission: RealRosterAdmission

    @property
    def field_tech(self) -> bool:
        return self.role in {
            RealRosterRole.FIELD_MANAGER,
            RealRosterRole.FIELD_TECH,
            RealRosterRole.HELPER,
        }

    @property
    def required_role_codes(self) -> frozenset[str]:
        return {
            RealRosterRole.ADMIN: frozenset({"COMPANY_ADMINISTRATOR"}),
            RealRosterRole.OFFICE_MANAGER: frozenset({"OFFICE_MANAGER"}),
            RealRosterRole.OFFICE_STAFF: frozenset({"SERVICE_CSR"}),
            RealRosterRole.FIELD_MANAGER: frozenset(
                {"FIELD_MANAGER", "TECHNICIAN", "ACP_EMPLOYEE_MOBILE", "DISPATCHER"}
            ),
            RealRosterRole.FIELD_TECH: frozenset({"TECHNICIAN", "ACP_EMPLOYEE_MOBILE"}),
            RealRosterRole.HELPER: frozenset({"TECHNICIAN", "ACP_EMPLOYEE_MOBILE"}),
        }[self.role]


REAL_ALL_COUNTY_ROSTER = (
    RealRosterPerson(
        "michael-fouse",
        "Michael Fouse",
        RealRosterRole.ADMIN,
        "pro_622e39dd3a544e4cb4fb8782ac767287",
        "allcountyleak@gmail.com",
        "allcountyleak@gmail.com",
        RealRosterAdmission.SAFE_CREATE,
    ),
    RealRosterPerson(
        "lianne-hernandez",
        "Lianne Hernandez",
        RealRosterRole.OFFICE_MANAGER,
        None,
        None,
        None,
        RealRosterAdmission.ALREADY_ACTIVE,
    ),
    RealRosterPerson(
        "alex-donahue",
        "Alex Donahue",
        RealRosterRole.FIELD_MANAGER,
        "pro_10853bfb63874a0b9d17cab14d1da20b",
        "alexallcountyleaks@gmail.com",
        "alexallcountyplumbingandleak@gmail.com",
        RealRosterAdmission.SAFE_CREATE,
    ),
    RealRosterPerson(
        "melvin-santiago",
        "Melvin Santiago",
        RealRosterRole.FIELD_TECH,
        "pro_23be6c33b14a4127bd737529180a56a1",
        "koqui360@gmail.com",
        "koqui360@gmail.com",
        RealRosterAdmission.SAFE_CREATE,
    ),
    RealRosterPerson(
        "dakota-wilcox",
        "Dakota Wilcox",
        RealRosterRole.FIELD_TECH,
        "pro_0ff2024a6baa4475a883f76d6cbcc58b",
        "dakotawilcox23@gmail.com",
        "dakotawilcox23@gmail.com",
        RealRosterAdmission.SAFE_CREATE,
    ),
    RealRosterPerson(
        "jason-calci",
        "Jason Calci",
        RealRosterRole.FIELD_TECH,
        "pro_6b2b2b7177a54187a690cb198a6dbda5",
        "jasoncalci27@gmail.com",
        "jasoncalci27@gmail.com",
        RealRosterAdmission.SAFE_CREATE,
    ),
    RealRosterPerson(
        "malcolm-calci",
        "Malcolm Calci",
        RealRosterRole.HELPER,
        None,
        "malcolmcalci04@gmail.com",
        "malcolmcalci04@gmail.com",
        RealRosterAdmission.OWNER_IDENTITY_DECISION_REQUIRED,
    ),
)

REAL_ALL_COUNTY_ROSTER_BY_KEY = {
    person.key: person for person in REAL_ALL_COUNTY_ROSTER
}

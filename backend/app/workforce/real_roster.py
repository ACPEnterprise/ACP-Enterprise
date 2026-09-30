from dataclasses import dataclass
from enum import StrEnum


class RealRosterRole(StrEnum):
    ADMIN = "ADMIN"
    OFFICE_MANAGER = "OFFICE_MANAGER"
    OFFICE_STAFF = "OFFICE_STAFF"
    FIELD_TECH = "FIELD_TECH"


class RealRosterAdmission(StrEnum):
    SAFE_CREATE = "SAFE_CREATE"
    ALREADY_ACTIVE = "ALREADY_ACTIVE"
    OWNER_IDENTITY_DECISION_REQUIRED = "OWNER_IDENTITY_DECISION_REQUIRED"


@dataclass(frozen=True, slots=True)
class RealRosterPerson:
    key: str
    display_name: str
    role: RealRosterRole
    source_employee_id: str | None
    source_login_email: str | None
    admission: RealRosterAdmission

    @property
    def field_tech(self) -> bool:
        return self.role is RealRosterRole.FIELD_TECH

    @property
    def required_role_codes(self) -> frozenset[str]:
        return {
            RealRosterRole.ADMIN: frozenset({"COMPANY_ADMINISTRATOR"}),
            RealRosterRole.OFFICE_MANAGER: frozenset({"OFFICE_MANAGER"}),
            RealRosterRole.OFFICE_STAFF: frozenset({"SERVICE_CSR"}),
            RealRosterRole.FIELD_TECH: frozenset({"TECHNICIAN", "ACP_EMPLOYEE_MOBILE"}),
        }[self.role]


REAL_ALL_COUNTY_ROSTER = (
    RealRosterPerson(
        "michael-fouse",
        "Michael Fouse",
        RealRosterRole.ADMIN,
        "pro_622e39dd3a544e4cb4fb8782ac767287",
        "allcountyleak@gmail.com",
        RealRosterAdmission.SAFE_CREATE,
    ),
    RealRosterPerson(
        "lianne-hernandez",
        "Lianne Hernandez",
        RealRosterRole.OFFICE_MANAGER,
        None,
        None,
        RealRosterAdmission.ALREADY_ACTIVE,
    ),
    RealRosterPerson(
        "alex-donahue",
        "Alex Donahue",
        RealRosterRole.OFFICE_STAFF,
        "pro_10853bfb63874a0b9d17cab14d1da20b",
        "alexallcountyleaks@gmail.com",
        RealRosterAdmission.OWNER_IDENTITY_DECISION_REQUIRED,
    ),
    RealRosterPerson(
        "melvin-santiago",
        "Melvin Santiago",
        RealRosterRole.FIELD_TECH,
        "pro_23be6c33b14a4127bd737529180a56a1",
        "koqui360@gmail.com",
        RealRosterAdmission.SAFE_CREATE,
    ),
    RealRosterPerson(
        "adam-mari",
        "Adam Mari",
        RealRosterRole.FIELD_TECH,
        "pro_4f1d81e3d31b4ffa9072dd6a32906586",
        "ajjmari3516@gmail.com",
        RealRosterAdmission.SAFE_CREATE,
    ),
    RealRosterPerson(
        "dareis-montgomery",
        "Dareis Montgomery",
        RealRosterRole.FIELD_TECH,
        "pro_2edf25dd14494b1885a50fa134b44fd8",
        "dareismontgomery37@gmail.com",
        RealRosterAdmission.SAFE_CREATE,
    ),
    RealRosterPerson(
        "dakota-wilcox",
        "Dakota Wilcox",
        RealRosterRole.FIELD_TECH,
        "pro_0ff2024a6baa4475a883f76d6cbcc58b",
        "dakotawilcox23@gmail.com",
        RealRosterAdmission.SAFE_CREATE,
    ),
    RealRosterPerson(
        "jason-calci",
        "Jason Calci",
        RealRosterRole.FIELD_TECH,
        "pro_6b2b2b7177a54187a690cb198a6dbda5",
        "jasoncalci27@gmail.com",
        RealRosterAdmission.SAFE_CREATE,
    ),
)

REAL_ALL_COUNTY_ROSTER_BY_KEY = {
    person.key: person for person in REAL_ALL_COUNTY_ROSTER
}

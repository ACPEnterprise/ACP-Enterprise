from dataclasses import dataclass
from enum import StrEnum


class RealRosterRole(StrEnum):
    ADMIN = "ADMIN"
    OFFICE_MANAGER = "OFFICE_MANAGER"
    OFFICE_STAFF = "OFFICE_STAFF"
    FIELD_TECH = "FIELD_TECH"


@dataclass(frozen=True, slots=True)
class RealRosterPerson:
    key: str
    display_name: str
    role: RealRosterRole

    @property
    def field_tech(self) -> bool:
        return self.role is RealRosterRole.FIELD_TECH

    @property
    def required_role_codes(self) -> frozenset[str]:
        return {
            RealRosterRole.ADMIN: frozenset({"COMPANY_ADMINISTRATOR"}),
            RealRosterRole.OFFICE_MANAGER: frozenset({"OFFICE_MANAGER"}),
            RealRosterRole.OFFICE_STAFF: frozenset({"SERVICE_CSR"}),
            RealRosterRole.FIELD_TECH: frozenset(
                {"TECHNICIAN", "ACP_EMPLOYEE_MOBILE"}
            ),
        }[self.role]


REAL_ALL_COUNTY_ROSTER = (
    RealRosterPerson("michael-fouse", "Michael Fouse", RealRosterRole.ADMIN),
    RealRosterPerson(
        "lianne-hernandez", "Lianne Hernandez", RealRosterRole.OFFICE_MANAGER
    ),
    RealRosterPerson("alex-donahue", "Alex Donahue", RealRosterRole.OFFICE_STAFF),
    RealRosterPerson("melvin-santiago", "Melvin Santiago", RealRosterRole.FIELD_TECH),
    RealRosterPerson("adam-mari", "Adam Mari", RealRosterRole.FIELD_TECH),
    RealRosterPerson(
        "dareis-montgomery", "Dareis Montgomery", RealRosterRole.FIELD_TECH
    ),
    RealRosterPerson("dakota-wilcox", "Dakota Wilcox", RealRosterRole.FIELD_TECH),
    RealRosterPerson("jason-calci", "Jason Calci", RealRosterRole.FIELD_TECH),
)

REAL_ALL_COUNTY_ROSTER_BY_KEY = {person.key: person for person in REAL_ALL_COUNTY_ROSTER}

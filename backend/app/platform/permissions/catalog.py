from dataclasses import dataclass
from enum import StrEnum
import re

from app.platform.permissions.codes import AdministrationPermission, CustomerPermission


CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


class PermissionScope(StrEnum):
    COMPANY = "company"
    PLATFORM = "platform"


@dataclass(frozen=True)
class PermissionDefinition:
    code: str
    name: str
    resource: str
    action: str
    scope: PermissionScope
    reserved: bool = False


class PermissionCatalogError(ValueError):
    pass


class PermissionCatalog:
    def __init__(self, definitions: tuple[PermissionDefinition, ...]) -> None:
        self.definitions = definitions

    def validate(self) -> None:
        seen: set[str] = set()
        for definition in self.definitions:
            if definition.code in seen:
                raise PermissionCatalogError(
                    f"Duplicate permission code: {definition.code}"
                )
            seen.add(definition.code)
            if not CODE_PATTERN.fullmatch(definition.code):
                raise PermissionCatalogError(
                    f"Invalid permission code: {definition.code}"
                )
            if (
                not definition.name.strip()
                or not definition.resource.strip()
                or not definition.action.strip()
            ):
                raise PermissionCatalogError(
                    f"Invalid permission definition: {definition.code}"
                )
            expected_prefix = (
                "COMPANY_"
                if definition.scope is PermissionScope.COMPANY
                else "PLATFORM_"
            )
            if not definition.code.startswith(expected_prefix):
                raise PermissionCatalogError(
                    f"Permission scope does not match code: {definition.code}"
                )
        reserved = {
            definition.code: definition
            for definition in self.definitions
            if definition.reserved
        }
        for code, definition in reserved.items():
            if definition.scope is not PermissionScope.COMPANY:
                raise PermissionCatalogError(
                    f"Reserved permission has invalid scope: {code}"
                )


ADMINISTRATION_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="company_access_policy",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
        reserved=True,
    )
    for code in sorted(AdministrationPermission.ALL)
)

CUSTOMER_DEFINITIONS = tuple(
    PermissionDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        resource="customer",
        action=code.rsplit("_", 1)[-1].lower(),
        scope=PermissionScope.COMPANY,
    )
    for code in sorted(CustomerPermission.ALL)
)

permission_catalog = PermissionCatalog(
    ADMINISTRATION_DEFINITIONS + CUSTOMER_DEFINITIONS
)

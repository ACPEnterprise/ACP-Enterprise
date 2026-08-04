from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.catalog import permission_catalog
from app.platform.permissions.models import Permission


class PersistedContractDriftError(RuntimeError):
    pass


@dataclass(frozen=True)
class PersistedPermissionReconciliation:
    unknown_company_codes: tuple[str, ...]


async def validate_persisted_permission_contract(
    session: AsyncSession,
) -> PersistedPermissionReconciliation:
    persisted = list(
        (
            await session.scalars(
                select(Permission).where(
                    Permission.status == "active", Permission.retired_at.is_(None)
                )
            )
        ).all()
    )
    by_code = {item.code: item for item in persisted}
    definitions = {item.code: item for item in permission_catalog.definitions}
    missing = sorted(set(definitions) - set(by_code))
    if missing:
        raise PersistedContractDriftError(
            "Canonical permissions are missing from persistence: " + ", ".join(missing)
        )
    mismatched = sorted(
        code
        for code, definition in definitions.items()
        if (
            by_code[code].name != definition.name
            or by_code[code].resource != definition.resource
            or by_code[code].action != definition.action
        )
    )
    if mismatched:
        raise PersistedContractDriftError(
            "Persisted permission metadata conflicts with the canonical catalog: "
            + ", ".join(mismatched)
        )
    unknown_company = tuple(
        sorted(
            item.code
            for item in persisted
            if item.code not in definitions and item.code.startswith("COMPANY_")
        )
    )
    return PersistedPermissionReconciliation(unknown_company)

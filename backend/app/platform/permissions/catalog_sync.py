from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.catalog import (
    PermissionCatalog,
    PermissionDefinition,
    permission_catalog,
)
from app.platform.permissions.models import Permission


PERMISSION_CATALOG_SYNC_LOCK_ID = 4_701_871_310_042_022


@dataclass(frozen=True)
class PermissionCatalogSyncItem:
    id: UUID
    code: str


@dataclass(frozen=True)
class PermissionCatalogSyncResult:
    created: tuple[PermissionCatalogSyncItem, ...]
    existing: tuple[PermissionCatalogSyncItem, ...]

    @property
    def created_codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.created)

    @property
    def existing_codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.existing)


class PermissionCatalogRepository:
    """Own persistence and locking for the canonical Permission catalog."""

    async def acquire_sync_lock(self, session: AsyncSession) -> None:
        await session.execute(
            select(func.pg_advisory_xact_lock(PERMISSION_CATALOG_SYNC_LOCK_ID))
        )

    async def get_by_codes(
        self, session: AsyncSession, *, codes: tuple[str, ...]
    ) -> tuple[Permission, ...]:
        return tuple(
            (
                await session.scalars(
                    select(Permission)
                    .where(Permission.code.in_(codes))
                    .order_by(Permission.code)
                )
            ).all()
        )

    @staticmethod
    def add_missing(
        session: AsyncSession, *, definitions: tuple[PermissionDefinition, ...]
    ) -> tuple[Permission, ...]:
        records = tuple(
            Permission(
                code=definition.code,
                name=definition.name,
                description=None,
                resource=definition.resource,
                action=definition.action,
                status="active",
            )
            for definition in definitions
        )
        session.add_all(records)
        return records


class PermissionCatalogSyncService:
    """Transactionally add missing canonical Permissions without changing grants."""

    def __init__(
        self,
        repository: PermissionCatalogRepository | None = None,
        catalog: PermissionCatalog = permission_catalog,
    ) -> None:
        self.repository = repository or PermissionCatalogRepository()
        self.catalog = catalog

    async def synchronize(self, session: AsyncSession) -> PermissionCatalogSyncResult:
        self.catalog.validate()
        definitions = tuple(
            sorted(self.catalog.definitions, key=lambda item: item.code)
        )
        codes = tuple(definition.code for definition in definitions)
        async with session.begin():
            await self.repository.acquire_sync_lock(session)
            existing = await self.repository.get_by_codes(session, codes=codes)
            existing_codes = frozenset(permission.code for permission in existing)
            missing = tuple(
                definition
                for definition in definitions
                if definition.code not in existing_codes
            )
            created = self.repository.add_missing(session, definitions=missing)
            await session.flush()
        return PermissionCatalogSyncResult(
            created=tuple(
                PermissionCatalogSyncItem(id=permission.id, code=permission.code)
                for permission in created
            ),
            existing=tuple(
                PermissionCatalogSyncItem(id=permission.id, code=permission.code)
                for permission in existing
            ),
        )


permission_catalog_sync_service = PermissionCatalogSyncService()

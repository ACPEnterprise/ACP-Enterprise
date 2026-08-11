import hashlib
import json
from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.branch.models import Branch
from app.platform.permissions.authorization import AuthorizationContext

from .errors import PriceBookConflict, PriceBookNotFound, PriceBookValidation
from .models import (
    PriceBookAuditEntry,
    PriceBookCategory,
    PriceBookCommercialSnapshot,
    PriceBookComponent,
    PriceBookOption,
    PriceBookOptionGroup,
    PriceBookPriceVersion,
    PriceBookServiceItem,
    PriceBookTaxClassification,
)
from .schemas import (
    AuditItem,
    CatalogPage,
    CategoryCreate,
    CategoryItem,
    ComponentItem,
    OptionCreate,
    OptionGroupCreate,
    OptionGroupItem,
    OptionItem,
    PriceVersionCreate,
    PriceVersionItem,
    PriceVersionUpdate,
    ServiceItem,
    ServiceItemCreate,
    SnapshotRequest,
    TaxClassificationCreate,
    TaxClassificationItem,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PriceBookService:
    @staticmethod
    def _audit(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        entity_type: str,
        entity_id: UUID,
        action: str,
        state: dict[str, object],
        reason: str,
        version: int,
        prior_state: dict[str, object] | None = None,
    ) -> None:
        session.add(
            PriceBookAuditEntry(
                company_id=context.company.id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor_user_id=context.user.id,
                new_state=state,
                prior_state=prior_state,
                reason=reason,
                version=version,
            )
        )

    async def catalog(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        branch_id: UUID | None = None,
    ) -> CatalogPage:
        if branch_id is not None and branch_id not in context.authorized_branch_ids:
            raise PriceBookNotFound("Branch was not found.")
        categories = tuple(
            (
                await session.scalars(
                    select(PriceBookCategory)
                    .where(
                        PriceBookCategory.company_id == context.company.id,
                        PriceBookCategory.status == "active",
                    )
                    .order_by(PriceBookCategory.name)
                )
            ).all()
        )
        taxes = tuple(
            (
                await session.scalars(
                    select(PriceBookTaxClassification)
                    .where(
                        PriceBookTaxClassification.company_id == context.company.id,
                        PriceBookTaxClassification.status == "active",
                    )
                    .order_by(PriceBookTaxClassification.name)
                )
            ).all()
        )
        item_query = select(PriceBookServiceItem).where(
            PriceBookServiceItem.company_id == context.company.id
        )
        if branch_id is not None:
            item_query = item_query.where(
                or_(
                    PriceBookServiceItem.branch_id.is_(None),
                    PriceBookServiceItem.branch_id == branch_id,
                )
            )
        items = tuple(
            (
                await session.scalars(item_query.order_by(PriceBookServiceItem.name))
            ).all()
        )
        item_ids = [item.id for item in items]
        versions = (
            tuple(
                (
                    await session.scalars(
                        select(PriceBookPriceVersion)
                        .where(
                            PriceBookPriceVersion.company_id == context.company.id,
                            PriceBookPriceVersion.service_item_id.in_(item_ids),
                        )
                        .order_by(
                            PriceBookPriceVersion.service_item_id,
                            PriceBookPriceVersion.revision.desc(),
                        )
                    )
                ).all()
            )
            if item_ids
            else ()
        )
        components = (
            tuple(
                (
                    await session.scalars(
                        select(PriceBookComponent)
                        .where(
                            PriceBookComponent.company_id == context.company.id,
                            PriceBookComponent.price_version_id.in_(
                                [v.id for v in versions]
                            ),
                        )
                        .order_by(
                            PriceBookComponent.price_version_id,
                            PriceBookComponent.position,
                        )
                    )
                ).all()
            )
            if versions
            else ()
        )
        by_version: dict[UUID, list[PriceBookComponent]] = {}
        for component in components:
            by_version.setdefault(component.price_version_id, []).append(component)
        option_groups = tuple(
            (
                await session.scalars(
                    select(PriceBookOptionGroup)
                    .where(PriceBookOptionGroup.company_id == context.company.id)
                    .order_by(PriceBookOptionGroup.name)
                )
            ).all()
        )
        options = tuple(
            (
                await session.scalars(
                    select(PriceBookOption)
                    .where(PriceBookOption.company_id == context.company.id)
                    .order_by(PriceBookOption.option_group_id, PriceBookOption.position)
                )
            ).all()
        )
        return CatalogPage(
            categories=tuple(
                CategoryItem.model_validate(value) for value in categories
            ),
            tax_classifications=tuple(
                TaxClassificationItem.model_validate(value) for value in taxes
            ),
            service_items=tuple(ServiceItem.model_validate(value) for value in items),
            versions=tuple(
                PriceVersionItem.model_validate(version).model_copy(
                    update={
                        "components": tuple(
                            ComponentItem.model_validate(c)
                            for c in by_version.get(version.id, [])
                        )
                    }
                )
                for version in versions
            ),
            option_groups=tuple(
                OptionGroupItem.model_validate(value) for value in option_groups
            ),
            options=tuple(OptionItem.model_validate(value) for value in options),
        )

    async def create_option_group(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: OptionGroupCreate,
    ) -> PriceBookOptionGroup:
        async with session.begin():
            group = PriceBookOptionGroup(
                company_id=context.company.id,
                code=payload.code,
                name=payload.name.strip(),
                minimum_selections=payload.minimum_selections,
                maximum_selections=payload.maximum_selections,
                created_by_user_id=context.user.id,
            )
            session.add(group)
            try:
                await session.flush()
            except IntegrityError as error:
                raise PriceBookConflict("Option group code already exists.") from error
            self._audit(
                session,
                context=context,
                entity_type="price_book_option_group",
                entity_id=group.id,
                action="created",
                state={"code": group.code},
                reason="Option group created.",
                version=1,
            )
        return group

    async def add_option(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        group_id: UUID,
        payload: OptionCreate,
    ) -> PriceBookOption:
        async with session.begin():
            group = await session.scalar(
                select(PriceBookOptionGroup).where(
                    PriceBookOptionGroup.id == group_id,
                    PriceBookOptionGroup.company_id == context.company.id,
                    PriceBookOptionGroup.status == "active",
                )
            )
            item = await session.scalar(
                select(PriceBookServiceItem).where(
                    PriceBookServiceItem.id == payload.service_item_id,
                    PriceBookServiceItem.company_id == context.company.id,
                )
            )
            if group is None or item is None:
                raise PriceBookNotFound("Option group or service item was not found.")
            option = PriceBookOption(
                company_id=context.company.id,
                option_group_id=group.id,
                service_item_id=item.id,
                label=payload.label.strip(),
                position=payload.position,
            )
            session.add(option)
            try:
                await session.flush()
            except IntegrityError as error:
                raise PriceBookConflict(
                    "Option or position already exists in this group."
                ) from error
            self._audit(
                session,
                context=context,
                entity_type="price_book_option",
                entity_id=option.id,
                action="created",
                state={
                    "option_group_id": str(group.id),
                    "service_item_id": str(item.id),
                },
                reason="Option added.",
                version=1,
            )
        return option

    async def create_category(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: CategoryCreate,
    ) -> PriceBookCategory:
        now = utc_now()
        async with session.begin():
            if payload.parent_id and not await session.scalar(
                select(PriceBookCategory.id).where(
                    PriceBookCategory.id == payload.parent_id,
                    PriceBookCategory.company_id == context.company.id,
                )
            ):
                raise PriceBookNotFound("Parent category was not found.")
            category = PriceBookCategory(
                company_id=context.company.id,
                parent_id=payload.parent_id,
                code=payload.code,
                name=payload.name.strip(),
                description=payload.description,
                created_by_user_id=context.user.id,
                created_at=now,
                updated_at=now,
            )
            session.add(category)
            try:
                await session.flush()
            except IntegrityError as error:
                raise PriceBookConflict("Category code already exists.") from error
            self._audit(
                session,
                context=context,
                entity_type="price_book_category",
                entity_id=category.id,
                action="created",
                state={"code": category.code, "status": category.status},
                reason="Category created.",
                version=1,
            )
        return category

    async def create_tax(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: TaxClassificationCreate,
    ) -> PriceBookTaxClassification:
        now = utc_now()
        async with session.begin():
            record = PriceBookTaxClassification(
                company_id=context.company.id,
                code=payload.code,
                name=payload.name.strip(),
                taxable=payload.taxable,
                created_by_user_id=context.user.id,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            try:
                await session.flush()
            except IntegrityError as error:
                raise PriceBookConflict(
                    "Tax classification code already exists."
                ) from error
            self._audit(
                session,
                context=context,
                entity_type="price_book_tax_classification",
                entity_id=record.id,
                action="created",
                state={"code": record.code, "taxable": record.taxable},
                reason="Tax classification created.",
                version=1,
            )
        return record

    async def create_item(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: ServiceItemCreate,
    ) -> PriceBookServiceItem:
        now = utc_now()
        async with session.begin():
            if not await session.scalar(
                select(PriceBookCategory.id).where(
                    PriceBookCategory.id == payload.category_id,
                    PriceBookCategory.company_id == context.company.id,
                    PriceBookCategory.status == "active",
                )
            ):
                raise PriceBookNotFound("Category was not found.")
            if payload.branch_id is not None and (
                payload.branch_id not in context.authorized_branch_ids
                or not await session.scalar(
                    select(Branch.id).where(
                        Branch.id == payload.branch_id,
                        Branch.company_id == context.company.id,
                        Branch.status == "active",
                    )
                )
            ):
                raise PriceBookNotFound("Branch was not found.")
            item = PriceBookServiceItem(
                company_id=context.company.id,
                branch_id=payload.branch_id,
                category_id=payload.category_id,
                code=payload.code,
                name=payload.name.strip(),
                customer_description=payload.customer_description.strip(),
                internal_description=payload.internal_description,
                created_by_user_id=context.user.id,
                created_at=now,
                updated_at=now,
            )
            session.add(item)
            try:
                await session.flush()
            except IntegrityError as error:
                raise PriceBookConflict("Service item code already exists.") from error
            self._audit(
                session,
                context=context,
                entity_type="price_book_service_item",
                entity_id=item.id,
                action="created",
                state={"code": item.code, "status": item.status},
                reason="Service item created.",
                version=1,
            )
        return item

    async def create_version(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        item_id: UUID,
        payload: PriceVersionCreate,
    ) -> PriceBookPriceVersion:
        if payload.expires_at and payload.expires_at <= payload.effective_at:
            raise PriceBookValidation("Expiration must follow the effective time.")
        now = utc_now()
        async with session.begin():
            item = await session.scalar(
                select(PriceBookServiceItem)
                .where(
                    PriceBookServiceItem.id == item_id,
                    PriceBookServiceItem.company_id == context.company.id,
                )
                .with_for_update()
            )
            if item is None:
                raise PriceBookNotFound("Service item was not found.")
            if (
                payload.branch_id is not None
                and payload.branch_id not in context.authorized_branch_ids
            ):
                raise PriceBookNotFound("Branch was not found.")
            if not await session.scalar(
                select(PriceBookTaxClassification.id).where(
                    PriceBookTaxClassification.id == payload.tax_classification_id,
                    PriceBookTaxClassification.company_id == context.company.id,
                    PriceBookTaxClassification.status == "active",
                )
            ):
                raise PriceBookNotFound("Tax classification was not found.")
            current_revision = await session.scalar(
                select(
                    func.coalesce(func.max(PriceBookPriceVersion.revision), 0)
                ).where(
                    PriceBookPriceVersion.company_id == context.company.id,
                    PriceBookPriceVersion.service_item_id == item.id,
                )
            )
            revision = (current_revision or 0) + 1
            version = PriceBookPriceVersion(
                company_id=context.company.id,
                service_item_id=item.id,
                branch_id=payload.branch_id,
                tax_classification_id=payload.tax_classification_id,
                revision=revision,
                currency=payload.currency,
                unit_price=payload.unit_price,
                effective_at=payload.effective_at,
                expires_at=payload.expires_at,
                created_by_user_id=context.user.id,
                created_at=now,
                updated_at=now,
            )
            session.add(version)
            await session.flush()
            for position, component in enumerate(payload.components, 1):
                session.add(
                    PriceBookComponent(
                        company_id=context.company.id,
                        price_version_id=version.id,
                        component_type=component.component_type,
                        code=component.code,
                        label=component.label.strip(),
                        quantity=component.quantity,
                        unit_cost=component.unit_cost,
                        position=position,
                    )
                )
            self._audit(
                session,
                context=context,
                entity_type="price_book_price_version",
                entity_id=version.id,
                action="draft_created",
                state={
                    "revision": revision,
                    "status": "draft",
                    "unit_price": str(version.unit_price),
                    "currency": version.currency,
                },
                reason="Draft price version created.",
                version=1,
            )
        return version

    async def update_draft(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        version_id: UUID,
        payload: PriceVersionUpdate,
    ) -> PriceBookPriceVersion:
        if payload.expires_at and payload.expires_at <= payload.effective_at:
            raise PriceBookValidation("Expiration must follow the effective time.")
        now = utc_now()
        async with session.begin():
            version = await session.scalar(
                select(PriceBookPriceVersion)
                .where(
                    PriceBookPriceVersion.id == version_id,
                    PriceBookPriceVersion.company_id == context.company.id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if version is None:
                raise PriceBookNotFound("Price version was not found.")
            if version.status != "draft" or version.version != payload.expected_version:
                raise PriceBookConflict("Only the current draft version may be edited.")
            if not await session.scalar(
                select(PriceBookTaxClassification.id).where(
                    PriceBookTaxClassification.id == payload.tax_classification_id,
                    PriceBookTaxClassification.company_id == context.company.id,
                    PriceBookTaxClassification.status == "active",
                )
            ):
                raise PriceBookNotFound("Tax classification was not found.")
            prior: dict[str, object] = {
                "unit_price": str(version.unit_price),
                "currency": version.currency,
                "effective_at": version.effective_at.isoformat(),
            }
            version.tax_classification_id = payload.tax_classification_id
            version.currency = payload.currency
            version.unit_price = payload.unit_price
            version.effective_at = payload.effective_at
            version.expires_at = payload.expires_at
            version.version += 1
            version.updated_at = now
            await session.execute(
                delete(PriceBookComponent).where(
                    PriceBookComponent.company_id == context.company.id,
                    PriceBookComponent.price_version_id == version.id,
                )
            )
            for position, component in enumerate(payload.components, 1):
                session.add(
                    PriceBookComponent(
                        company_id=context.company.id,
                        price_version_id=version.id,
                        component_type=component.component_type,
                        code=component.code,
                        label=component.label.strip(),
                        quantity=component.quantity,
                        unit_cost=component.unit_cost,
                        position=position,
                    )
                )
            self._audit(
                session,
                context=context,
                entity_type="price_book_price_version",
                entity_id=version.id,
                action="draft_updated",
                prior_state=prior,
                state={
                    "unit_price": str(version.unit_price),
                    "currency": version.currency,
                    "effective_at": version.effective_at.isoformat(),
                },
                reason="Draft price version corrected.",
                version=version.version,
            )
        return version

    async def activate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        version_id: UUID,
        expected_version: int,
        reason: str,
    ) -> PriceBookPriceVersion:
        now = utc_now()
        async with session.begin():
            target = await session.scalar(
                select(PriceBookPriceVersion)
                .where(
                    PriceBookPriceVersion.id == version_id,
                    PriceBookPriceVersion.company_id == context.company.id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if target is None:
                raise PriceBookNotFound("Price version was not found.")
            if (
                target.status == "active"
                and target.version == expected_version + 1
                and target.activation_reason == reason
            ):
                return target
            if target.status != "draft" or target.version != expected_version:
                raise PriceBookConflict(
                    "Price version changed or is not an activatable draft."
                )
            item = await session.scalar(
                select(PriceBookServiceItem)
                .where(
                    PriceBookServiceItem.id == target.service_item_id,
                    PriceBookServiceItem.company_id == context.company.id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if item is None:
                raise PriceBookNotFound("Service item was not found.")
            overlap = and_(
                PriceBookPriceVersion.effective_at
                < (target.expires_at or datetime.max.replace(tzinfo=timezone.utc)),
                or_(
                    PriceBookPriceVersion.expires_at.is_(None),
                    PriceBookPriceVersion.expires_at > target.effective_at,
                ),
            )
            active = tuple(
                (
                    await session.scalars(
                        select(PriceBookPriceVersion)
                        .where(
                            PriceBookPriceVersion.company_id == context.company.id,
                            PriceBookPriceVersion.service_item_id
                            == target.service_item_id,
                            PriceBookPriceVersion.branch_id.is_not_distinct_from(
                                target.branch_id
                            ),
                            PriceBookPriceVersion.status == "active",
                            PriceBookPriceVersion.id != target.id,
                            overlap,
                        )
                        .with_for_update()
                    )
                ).all()
            )
            if len(active) > 1:
                raise PriceBookConflict(
                    "Existing active price state requires reconciliation."
                )
            for prior in active:
                if prior.effective_at >= target.effective_at:
                    raise PriceBookConflict(
                        "The new effective time does not supersede the active version."
                    )
                prior.status = "superseded"
                prior.expires_at = target.effective_at
                prior.version += 1
                prior.updated_at = now
                self._audit(
                    session,
                    context=context,
                    entity_type="price_book_price_version",
                    entity_id=prior.id,
                    action="superseded",
                    state={
                        "status": prior.status,
                        "expires_at": target.effective_at.isoformat(),
                    },
                    reason=reason,
                    version=prior.version,
                )
            target.status = "active"
            target.activated_by_user_id = context.user.id
            target.activated_at = now
            target.activation_reason = reason
            target.version += 1
            target.updated_at = now
            item.status = "active"
            item.current_version_id = target.id
            item.version += 1
            item.updated_at = now
            self._audit(
                session,
                context=context,
                entity_type="price_book_price_version",
                entity_id=target.id,
                action="activated",
                state={
                    "status": target.status,
                    "revision": target.revision,
                    "effective_at": target.effective_at.isoformat(),
                },
                reason=reason,
                version=target.version,
            )
            BusinessEventService.stage(
                session,
                BusinessEventCreate(
                    event_type=EventType.PRICE_BOOK_PRICE_VERSION_ACTIVATED,
                    entity_type="price_book_price_version",
                    entity_id=target.id,
                    company_id=context.company.id,
                    branch_id=target.branch_id,
                    user_id=context.user.id,
                    payload={
                        "service_item_id": str(item.id),
                        "price_version_id": str(target.id),
                        "item_code": item.code,
                        "currency": target.currency,
                        "effective_at": target.effective_at.isoformat(),
                        "expires_at": target.expires_at.isoformat()
                        if target.expires_at
                        else None,
                        "tax_classification_id": str(target.tax_classification_id),
                    },
                ),
            )
        return target

    async def transition_lifecycle(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        version_id: UUID,
        target_status: str,
        expected_version: int,
        reason: str,
    ) -> PriceBookPriceVersion:
        allowed: dict[str, frozenset[str]] = {
            "inactive": frozenset({"active"}),
            "archived": frozenset({"draft", "inactive", "superseded"}),
        }
        if target_status not in allowed:
            raise PriceBookValidation("Unsupported lifecycle transition.")
        now = utc_now()
        async with session.begin():
            target = await session.scalar(
                select(PriceBookPriceVersion)
                .where(
                    PriceBookPriceVersion.id == version_id,
                    PriceBookPriceVersion.company_id == context.company.id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if target is None:
                raise PriceBookNotFound("Price version was not found.")
            if (
                target.status == target_status
                and target.version == expected_version + 1
            ):
                return target
            if (
                target.version != expected_version
                or target.status not in allowed[target_status]
            ):
                raise PriceBookConflict(
                    f"Price version cannot transition from {target.status} to {target_status}."
                )
            prior_status = target.status
            target.status = target_status
            target.version += 1
            target.updated_at = now
            item = await session.scalar(
                select(PriceBookServiceItem)
                .where(
                    PriceBookServiceItem.id == target.service_item_id,
                    PriceBookServiceItem.company_id == context.company.id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if item is None:
                raise PriceBookConflict("Service item state is unavailable.")
            if item.current_version_id == target.id:
                item.current_version_id = None
                item.status = "inactive" if target_status == "inactive" else "archived"
                item.version += 1
                item.updated_at = now
            self._audit(
                session,
                context=context,
                entity_type="price_book_price_version",
                entity_id=target.id,
                action=target_status,
                prior_state={"status": prior_status},
                state={"status": target_status},
                reason=reason,
                version=target.version,
            )
        return target

    async def get_snapshot(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        snapshot_id: UUID,
    ) -> PriceBookCommercialSnapshot:
        snapshot = await session.scalar(
            select(PriceBookCommercialSnapshot).where(
                PriceBookCommercialSnapshot.id == snapshot_id,
                PriceBookCommercialSnapshot.company_id == context.company.id,
                PriceBookCommercialSnapshot.branch_id.in_(
                    context.authorized_branch_ids
                ),
            )
        )
        if snapshot is None:
            raise PriceBookNotFound("Commercial snapshot was not found.")
        return snapshot

    async def audit_history(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        entity_id: UUID | None = None,
    ) -> tuple[AuditItem, ...]:
        query = select(PriceBookAuditEntry).where(
            PriceBookAuditEntry.company_id == context.company.id
        )
        if entity_id is not None:
            query = query.where(PriceBookAuditEntry.entity_id == entity_id)
        records = tuple(
            (
                await session.scalars(
                    query.order_by(
                        PriceBookAuditEntry.occurred_at.desc(), PriceBookAuditEntry.id
                    )
                )
            ).all()
        )
        return tuple(AuditItem.model_validate(record) for record in records)

    async def snapshot(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        item_id: UUID,
        payload: SnapshotRequest,
    ) -> PriceBookCommercialSnapshot:
        if payload.branch_id not in context.authorized_branch_ids:
            raise PriceBookNotFound("Branch was not found.")
        async with session.begin():
            existing = await session.scalar(
                select(PriceBookCommercialSnapshot).where(
                    PriceBookCommercialSnapshot.company_id == context.company.id,
                    PriceBookCommercialSnapshot.idempotency_key
                    == payload.idempotency_key,
                )
            )
            if existing:
                if (
                    existing.service_item_id != item_id
                    or existing.branch_id != payload.branch_id
                    or existing.quantity != payload.quantity
                    or existing.currency != payload.currency
                    or existing.effective_at != payload.effective_at
                    or existing.snapshot_data.get("option_group_id")
                    != (
                        str(payload.option_group_id)
                        if payload.option_group_id
                        else None
                    )
                    or existing.snapshot_data.get("option_id")
                    != (str(payload.option_id) if payload.option_id else None)
                    or existing.snapshot_data.get("historical") != payload.historical
                ):
                    raise PriceBookConflict(
                        "Idempotency key was already used for a different snapshot request."
                    )
                return existing
            item = await session.scalar(
                select(PriceBookServiceItem).where(
                    PriceBookServiceItem.id == item_id,
                    PriceBookServiceItem.company_id == context.company.id,
                    PriceBookServiceItem.status == "active",
                )
            )
            if item is None or (
                item.branch_id is not None and item.branch_id != payload.branch_id
            ):
                raise PriceBookNotFound("Eligible service item was not found.")
            if (payload.option_group_id is None) != (payload.option_id is None):
                raise PriceBookValidation(
                    "Option group and option must be supplied together."
                )
            selected_option: PriceBookOption | None = None
            selected_option_group: PriceBookOptionGroup | None = None
            if payload.option_id is not None and payload.option_group_id is not None:
                selected_option = await session.scalar(
                    select(PriceBookOption).where(
                        PriceBookOption.id == payload.option_id,
                        PriceBookOption.company_id == context.company.id,
                        PriceBookOption.option_group_id == payload.option_group_id,
                        PriceBookOption.service_item_id == item.id,
                    )
                )
                if selected_option is None:
                    raise PriceBookNotFound("Selected customer option was not found.")
                selected_option_group = await session.scalar(
                    select(PriceBookOptionGroup).where(
                        PriceBookOptionGroup.id == payload.option_group_id,
                        PriceBookOptionGroup.company_id == context.company.id,
                        PriceBookOptionGroup.status == "active",
                    )
                )
                if selected_option_group is None:
                    raise PriceBookNotFound("Selected option group was not found.")
            eligible_statuses = (
                ("active", "superseded") if payload.historical else ("active",)
            )
            candidates = tuple(
                (
                    await session.scalars(
                        select(PriceBookPriceVersion)
                        .where(
                            PriceBookPriceVersion.company_id == context.company.id,
                            PriceBookPriceVersion.service_item_id == item.id,
                            PriceBookPriceVersion.status.in_(eligible_statuses),
                            PriceBookPriceVersion.currency == payload.currency,
                            PriceBookPriceVersion.effective_at <= payload.effective_at,
                            or_(
                                PriceBookPriceVersion.expires_at.is_(None),
                                PriceBookPriceVersion.expires_at > payload.effective_at,
                            ),
                            or_(
                                PriceBookPriceVersion.branch_id == payload.branch_id,
                                PriceBookPriceVersion.branch_id.is_(None),
                            ),
                        )
                        .order_by(PriceBookPriceVersion.branch_id.desc().nullslast())
                    )
                ).all()
            )
            scoped = [v for v in candidates if v.branch_id == payload.branch_id] or [
                v for v in candidates if v.branch_id is None
            ]
            if len(scoped) != 1:
                raise PriceBookConflict("Price selection is unavailable or ambiguous.")
            version = scoped[0]
            tax = await session.get(
                PriceBookTaxClassification, version.tax_classification_id
            )
            if tax is None or tax.company_id != context.company.id:
                raise PriceBookConflict("Tax classification is unavailable.")
            components = tuple(
                (
                    await session.scalars(
                        select(PriceBookComponent)
                        .where(
                            PriceBookComponent.company_id == context.company.id,
                            PriceBookComponent.price_version_id == version.id,
                        )
                        .order_by(PriceBookComponent.position)
                    )
                ).all()
            )
            extended = (
                Decimal(payload.quantity) * Decimal(version.unit_price)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
            data: dict[str, object] = {
                "service_item_id": str(item.id),
                "price_version_id": str(version.id),
                "item_code": item.code,
                "description": item.customer_description,
                "quantity": str(payload.quantity),
                "unit_price": str(version.unit_price),
                "extended_amount": str(extended),
                "currency": version.currency,
                "rounding_mode": version.rounding_mode,
                "tax_classification": {
                    "id": str(tax.id),
                    "code": tax.code,
                    "taxable": tax.taxable,
                },
                "components": [
                    {
                        "type": c.component_type,
                        "code": c.code,
                        "label": c.label,
                        "quantity": str(c.quantity),
                    }
                    for c in components
                ],
                "effective_at": payload.effective_at.isoformat(),
                "historical": payload.historical,
                "option_group_id": str(payload.option_group_id)
                if payload.option_group_id
                else None,
                "option_id": str(selected_option.id) if selected_option else None,
                "option_group_constraints": (
                    {
                        "minimum_selections": selected_option_group.minimum_selections,
                        "maximum_selections": selected_option_group.maximum_selections,
                    }
                    if selected_option_group
                    else None
                ),
            }
            digest = hashlib.sha256(
                json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            snapshot = PriceBookCommercialSnapshot(
                company_id=context.company.id,
                branch_id=payload.branch_id,
                service_item_id=item.id,
                price_version_id=version.id,
                quantity=payload.quantity,
                unit_price=version.unit_price,
                extended_amount=extended,
                currency=version.currency,
                effective_at=payload.effective_at,
                snapshot_data=data,
                digest=digest,
                idempotency_key=payload.idempotency_key,
                created_by_user_id=context.user.id,
            )
            session.add(snapshot)
            await session.flush()
            self._audit(
                session,
                context=context,
                entity_type="price_book_commercial_snapshot",
                entity_id=snapshot.id,
                action="created",
                state={"digest": digest, "price_version_id": str(version.id)},
                reason="Immutable commercial snapshot created.",
                version=1,
            )
        return snapshot


price_book_service = PriceBookService()

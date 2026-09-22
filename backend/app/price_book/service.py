import hashlib
import json
from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.branch.models import Branch
from app.platform.idempotency.contracts import (
    IdempotencyIdentity,
    canonical_request_digest,
)
from app.platform.idempotency.reliability import (
    AuthoritativeOutcome,
    RetentionClass,
    mutation_reliability_service,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import PriceBookPermission

from .errors import PriceBookConflict, PriceBookNotFound, PriceBookValidation
from .models import (
    PriceBookActivationReview,
    PriceBookAdjustmentProposal,
    PriceBookAuditEntry,
    PriceBookCandidateBinding,
    PriceBookCategory,
    PriceBookCommercialSnapshot,
    PriceBookComponent,
    PriceBookOption,
    PriceBookOptionGroup,
    PriceBookPriceVersion,
    PriceBookReviewBatch,
    PriceBookServiceItem,
    PriceBookTaxClassification,
)
from .schemas import (
    ActivationReadinessItem,
    AdjustmentProposalCreate,
    AdjustmentProposalDecision,
    AuditItem,
    BulkMaterializeItem,
    BulkMaterializeRequest,
    CatalogPage,
    CategoryCreate,
    CategoryItem,
    CategoryUpdate,
    ComponentItem,
    OptionCreate,
    OptionGroupCreate,
    OptionGroupItem,
    OptionItem,
    PriceVersionCreate,
    PriceVersionItem,
    PriceVersionUpdate,
    ReviewBatchCreate,
    ReviewBatchDecision,
    ServiceItem,
    ServiceItemCreate,
    ServiceItemUpdate,
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
        search: str | None = None,
        category_id: UUID | None = None,
        item_status: str | None = None,
        version_status: str | None = None,
        sellable_only: bool = False,
        sellable_at: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> CatalogPage:
        if branch_id is not None and branch_id not in context.authorized_branch_ids:
            raise PriceBookNotFound("Branch was not found.")
        categories = tuple(
            (
                await session.scalars(
                    select(PriceBookCategory)
                    .where(
                        PriceBookCategory.company_id == context.company.id,
                        PriceBookCategory.status.in_(("draft", "active")),
                    )
                    .order_by(
                        PriceBookCategory.position.asc().nullslast(),
                        PriceBookCategory.name,
                    )
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

        def category_tree(seed_ids: set[UUID]) -> set[UUID]:
            """Return the selected categories and every visible descendant."""
            expanded = set(seed_ids)
            while True:
                descendants = {
                    category.id
                    for category in categories
                    if category.parent_id in expanded
                }
                if descendants.issubset(expanded):
                    return expanded
                expanded.update(descendants)

        if sellable_only:
            item_status = "active"
            version_status = "active"
            resolved_sellable_at = sellable_at or utc_now()
            item_query = item_query.where(
                PriceBookServiceItem.current_version_id.is_not(None),
                PriceBookServiceItem.current_version_id.in_(
                    select(PriceBookPriceVersion.id).where(
                        PriceBookPriceVersion.company_id == context.company.id,
                        PriceBookPriceVersion.status == "active",
                        PriceBookPriceVersion.effective_at <= resolved_sellable_at,
                        or_(
                            PriceBookPriceVersion.expires_at.is_(None),
                            PriceBookPriceVersion.expires_at > resolved_sellable_at,
                        ),
                    )
                ),
            )
        if branch_id is not None:
            item_query = item_query.where(
                or_(
                    PriceBookServiceItem.branch_id.is_(None),
                    PriceBookServiceItem.branch_id == branch_id,
                )
            )
        if category_id is not None:
            item_query = item_query.where(
                PriceBookServiceItem.category_id.in_(category_tree({category_id}))
            )
        if item_status is not None:
            item_query = item_query.where(PriceBookServiceItem.status == item_status)
        if search:
            normalized_search = search.strip()
            term = f"%{normalized_search}%"
            category_term = normalized_search.casefold()
            matching_category_ids = category_tree(
                {
                    category.id
                    for category in categories
                    if category_term in category.code.casefold()
                    or category_term in category.name.casefold()
                }
            )
            item_query = item_query.where(
                or_(
                    PriceBookServiceItem.code.ilike(term),
                    PriceBookServiceItem.name.ilike(term),
                    PriceBookServiceItem.customer_description.ilike(term),
                    PriceBookServiceItem.category_id.in_(matching_category_ids),
                )
            )
        total_items = int(
            await session.scalar(
                select(func.count()).select_from(item_query.subquery())
            )
            or 0
        )
        if sellable_only:
            filtered_items = item_query.subquery()
            visible_category_ids = set(
                (
                    await session.scalars(
                        select(filtered_items.c.category_id).distinct()
                    )
                ).all()
            )
            by_category_id = {category.id: category for category in categories}
            while True:
                parent_ids = {
                    by_category_id[visible_id].parent_id
                    for visible_id in visible_category_ids
                    if visible_id in by_category_id
                    and by_category_id[visible_id].parent_id is not None
                }
                new_parent_ids = parent_ids.difference(visible_category_ids)
                if not new_parent_ids:
                    break
                visible_category_ids.update(new_parent_ids)
            categories = tuple(
                category
                for category in categories
                if category.id in visible_category_ids
            )
        items = tuple(
            (
                await session.scalars(
                    item_query.order_by(
                        PriceBookServiceItem.name, PriceBookServiceItem.id
                    )
                    .limit(limit)
                    .offset(offset)
                )
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
                            *(
                                (PriceBookPriceVersion.status == version_status,)
                                if version_status
                                else ()
                            ),
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
        option_query = select(PriceBookOption).where(
            PriceBookOption.company_id == context.company.id
        )
        if sellable_only:
            option_query = option_query.where(
                PriceBookOption.service_item_id.in_(item_ids)
            )
        options = tuple(
            (
                await session.scalars(
                    option_query.order_by(
                        PriceBookOption.option_group_id, PriceBookOption.position
                    )
                )
            ).all()
        )
        option_group_query = select(PriceBookOptionGroup).where(
            PriceBookOptionGroup.company_id == context.company.id
        )
        if sellable_only:
            option_group_query = option_group_query.where(
                PriceBookOptionGroup.status == "active",
                PriceBookOptionGroup.id.in_(
                    [option.option_group_id for option in options]
                ),
            )
        option_groups = tuple(
            (
                await session.scalars(
                    option_group_query.order_by(PriceBookOptionGroup.name)
                )
            ).all()
        )
        costs_visible = context.has_permission(PriceBookPermission.MANAGE)
        return CatalogPage(
            categories=tuple(
                CategoryItem.model_validate(value) for value in categories
            ),
            tax_classifications=tuple(
                TaxClassificationItem.model_validate(value) for value in taxes
            ),
            service_items=tuple(
                ServiceItem.model_validate(value).model_copy(
                    update={
                        "internal_description": (
                            value.internal_description if costs_visible else None
                        )
                    }
                )
                for value in items
            ),
            versions=tuple(
                self._version_item(
                    version,
                    by_version.get(version.id, []),
                    costs_visible=costs_visible,
                )
                for version in versions
            ),
            option_groups=tuple(
                OptionGroupItem.model_validate(value) for value in option_groups
            ),
            options=tuple(OptionItem.model_validate(value) for value in options),
            total_service_items=total_items,
            limit=limit,
            offset=offset,
            costs_visible=costs_visible,
        )

    @staticmethod
    def _version_item(
        version: PriceBookPriceVersion,
        components: list[PriceBookComponent],
        *,
        costs_visible: bool,
    ) -> PriceVersionItem:
        complete = bool(components) and all(c.unit_cost is not None for c in components)
        total = (
            sum(
                (
                    c.quantity * c.unit_cost
                    for c in components
                    if c.unit_cost is not None
                ),
                Decimal(0),
            )
            if complete
            else None
        )
        return PriceVersionItem.model_validate(version).model_copy(
            update={
                "components": tuple(
                    ComponentItem.model_validate(c).model_copy(
                        update={
                            "unit_cost": c.unit_cost if costs_visible else None,
                            "extended_cost": c.quantity * c.unit_cost
                            if costs_visible and c.unit_cost is not None
                            else None,
                        }
                    )
                    for c in components
                ),
                "cost_readiness": "COST_COMPLETE"
                if complete
                else "INSUFFICIENT_COST_EVIDENCE",
                "expected_direct_cost": total if costs_visible else None,
                "expected_direct_contribution": version.unit_price - total
                if costs_visible and total is not None
                else None,
            }
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
                position=payload.position,
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

    async def update_category(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        category_id: UUID,
        payload: CategoryUpdate,
    ) -> PriceBookCategory:
        async with session.begin():
            category = await session.scalar(
                select(PriceBookCategory)
                .where(
                    PriceBookCategory.id == category_id,
                    PriceBookCategory.company_id == context.company.id,
                )
                .with_for_update()
            )
            if category is None:
                raise PriceBookNotFound("Category was not found.")
            if category.version != payload.expected_version:
                raise PriceBookConflict("Category authority is stale.")
            if payload.parent_id == category.id:
                raise PriceBookValidation("Category cannot be its own parent.")
            if payload.parent_id is not None and not await session.scalar(
                select(PriceBookCategory.id).where(
                    PriceBookCategory.id == payload.parent_id,
                    PriceBookCategory.company_id == context.company.id,
                    PriceBookCategory.status.in_(("draft", "active")),
                )
            ):
                raise PriceBookNotFound("Parent category was not found.")
            prior: dict[str, object] = {
                "code": category.code,
                "name": category.name,
                "status": category.status,
            }
            category.code = payload.code
            category.name = payload.name.strip()
            category.description = payload.description
            category.parent_id = payload.parent_id
            category.position = payload.position
            category.status = payload.status
            category.version += 1
            category.updated_at = utc_now()
            try:
                await session.flush()
            except IntegrityError as error:
                raise PriceBookConflict("Category code already exists.") from error
            self._audit(
                session,
                context=context,
                entity_type="price_book_category",
                entity_id=category.id,
                action="updated",
                prior_state=prior,
                state={
                    "code": category.code,
                    "name": category.name,
                    "status": category.status,
                },
                reason="Category maintained by authorized operator.",
                version=category.version,
            )
        return category

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
                    PriceBookCategory.status.in_(("draft", "active")),
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

    async def update_item(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        item_id: UUID,
        payload: ServiceItemUpdate,
    ) -> PriceBookServiceItem:
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
            if item.version != payload.expected_version:
                raise PriceBookConflict("Service item authority is stale.")
            if not await session.scalar(
                select(PriceBookCategory.id).where(
                    PriceBookCategory.id == payload.category_id,
                    PriceBookCategory.company_id == context.company.id,
                    PriceBookCategory.status.in_(("draft", "active")),
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
            prior: dict[str, object] = {
                "code": item.code,
                "name": item.name,
                "status": item.status,
                "category_id": str(item.category_id),
            }
            item.branch_id = payload.branch_id
            item.category_id = payload.category_id
            item.code = payload.code
            item.name = payload.name.strip()
            item.customer_description = payload.customer_description.strip()
            if "internal_description" in payload.model_fields_set:
                item.internal_description = payload.internal_description
            item.status = payload.status
            item.version += 1
            item.updated_at = utc_now()
            try:
                await session.flush()
            except IntegrityError as error:
                raise PriceBookConflict("Service item code already exists.") from error
            self._audit(
                session,
                context=context,
                entity_type="price_book_service_item",
                entity_id=item.id,
                action="updated",
                prior_state=prior,
                state={
                    "code": item.code,
                    "name": item.name,
                    "status": item.status,
                    "category_id": str(item.category_id),
                },
                reason="Service item maintained by authorized operator.",
                version=item.version,
            )
        return item

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
            binding = await session.scalar(
                select(PriceBookCandidateBinding).where(
                    PriceBookCandidateBinding.company_id == context.company.id,
                    PriceBookCandidateBinding.entity_type == "service",
                    PriceBookCandidateBinding.native_entity_id
                    == target.service_item_id,
                )
            )
            if binding is not None:
                review = await session.scalar(
                    select(PriceBookActivationReview).where(
                        PriceBookActivationReview.company_id == context.company.id,
                        PriceBookActivationReview.price_version_id == target.id,
                    )
                )
                if review is None or review.draft_version != target.version:
                    raise PriceBookConflict("Candidate approvals are missing or stale.")
                if not all(
                    (
                        review.price_approved_at,
                        review.tax_approved_at,
                        review.effective_approved_at,
                        review.activation_authorized_at,
                    )
                ):
                    raise PriceBookConflict(
                        "Candidate activation requirements remain unresolved."
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

    async def activation_readiness(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        version_id: UUID,
    ) -> ActivationReadinessItem:
        version = await session.scalar(
            select(PriceBookPriceVersion).where(
                PriceBookPriceVersion.company_id == context.company.id,
                PriceBookPriceVersion.id == version_id,
            )
        )
        if version is None:
            raise PriceBookNotFound("Price version was not found.")
        binding = await session.scalar(
            select(PriceBookCandidateBinding).where(
                PriceBookCandidateBinding.company_id == context.company.id,
                PriceBookCandidateBinding.entity_type == "service",
                PriceBookCandidateBinding.native_entity_id == version.service_item_id,
            )
        )
        if binding is None:
            raise PriceBookNotFound("Candidate review evidence was not found.")
        review = await session.scalar(
            select(PriceBookActivationReview).where(
                PriceBookActivationReview.company_id == context.company.id,
                PriceBookActivationReview.price_version_id == version.id,
            )
        )
        current_review = (
            review
            if review is not None and review.draft_version == version.version
            else None
        )
        states = {
            "PRICE_APPROVAL_REQUIRED": bool(
                current_review and current_review.price_approved_at
            ),
            "TAX_REVIEW_REQUIRED": bool(
                current_review and current_review.tax_approved_at
            ),
            "EFFECTIVE_DATE_REQUIRED": bool(
                current_review and current_review.effective_approved_at
            ),
            "ACTIVATION_AUTHORIZATION_REQUIRED": bool(
                current_review and current_review.activation_authorized_at
            ),
        }
        conflict = "SOURCE_CONFLICT" in binding.review_flags
        blockers = [key for key, resolved in states.items() if not resolved]
        if conflict:
            blockers.append("SOURCE_CONFLICT")
        evidence = binding.candidate_evidence
        return ActivationReadinessItem(
            price_version_id=version.id,
            draft_version=version.version,
            candidate_identity=binding.candidate_identity,
            service_code=str(evidence.get("service_code", "")),
            price_approved=states["PRICE_APPROVAL_REQUIRED"],
            tax_approved=states["TAX_REVIEW_REQUIRED"],
            effective_date_approved=states["EFFECTIVE_DATE_REQUIRED"],
            activation_authorized=states["ACTIVATION_AUTHORIZATION_REQUIRED"],
            material_mapping_required="MATERIAL_MAPPING_REQUIRED"
            in binding.review_flags,
            source_conflict=conflict,
            activation_ready=not blockers,
            remaining_blockers=tuple(blockers),
            rationale={
                key: str(value) for key, value in current_review.rationale.items()
            }
            if current_review
            else {},
        )

    async def record_activation_review(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        version_id: UUID,
        expected_version: int,
        decision: str,
        reason: str,
        idempotency_key: str,
    ) -> ActivationReadinessItem:
        async def mutate() -> AuthoritativeOutcome[PriceBookPriceVersion]:
            version = await self._stage_activation_review(
                session,
                context=context,
                version_id=version_id,
                expected_version=expected_version,
                decision=decision,
                reason=reason,
            )
            return AuthoritativeOutcome(
                version,
                "price_book_price_version",
                version.id,
                200,
            )

        async def recover(result_id: UUID) -> PriceBookPriceVersion | None:
            return await session.scalar(
                select(PriceBookPriceVersion).where(
                    PriceBookPriceVersion.company_id == context.company.id,
                    PriceBookPriceVersion.id == result_id,
                )
            )

        await mutation_reliability_service.execute(
            session,
            identity=IdempotencyIdentity(
                company_id=context.company.id,
                branch_id=context.active_branch.id if context.active_branch else None,
                operation=f"price_book.activation_review.{decision}",
                idempotency_key=idempotency_key,
            ),
            actor_user_id=context.user.id,
            request_digest=canonical_request_digest(
                {
                    "version_id": version_id,
                    "expected_version": expected_version,
                    "decision": decision,
                    "reason": reason,
                }
            ),
            retention_class=RetentionClass.FINANCIAL_AUDIT,
            mutate=mutate,
            recover=recover,
        )
        return await self.activation_readiness(
            session, context=context, version_id=version_id
        )

    async def _stage_activation_review(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        version_id: UUID,
        expected_version: int,
        decision: str,
        reason: str,
    ) -> PriceBookPriceVersion:
        allowed = {"price", "tax", "effective_date", "activation_authorization"}
        if decision not in allowed:
            raise PriceBookValidation("Unsupported activation review decision.")
        now = utc_now()
        version = await session.scalar(
            select(PriceBookPriceVersion)
            .where(
                PriceBookPriceVersion.company_id == context.company.id,
                PriceBookPriceVersion.id == version_id,
            )
            .with_for_update()
        )
        if version is None:
            raise PriceBookNotFound("Price version was not found.")
        if version.status != "draft" or version.version != expected_version:
            raise PriceBookConflict("Only the current draft may be approved.")
        binding = await session.scalar(
            select(PriceBookCandidateBinding).where(
                PriceBookCandidateBinding.company_id == context.company.id,
                PriceBookCandidateBinding.entity_type == "service",
                PriceBookCandidateBinding.native_entity_id == version.service_item_id,
            )
        )
        if binding is None or "SOURCE_CONFLICT" in binding.review_flags:
            raise PriceBookConflict("Candidate source authority is not approvable.")
        review = await session.scalar(
            select(PriceBookActivationReview)
            .where(
                PriceBookActivationReview.company_id == context.company.id,
                PriceBookActivationReview.price_version_id == version.id,
            )
            .with_for_update()
        )
        if review is None:
            review = PriceBookActivationReview(
                company_id=context.company.id,
                price_version_id=version.id,
                draft_version=version.version,
                rationale={},
            )
            session.add(review)
        elif review.draft_version != version.version:
            review.draft_version = version.version
            review.price_approved_by_user_id = review.tax_approved_by_user_id = None
            review.effective_approved_by_user_id = (
                review.activation_authorized_by_user_id
            ) = None
            review.price_approved_at = review.tax_approved_at = None
            review.effective_approved_at = review.activation_authorized_at = None
            review.rationale = {}
        if decision == "activation_authorization" and not all(
            (
                review.price_approved_at,
                review.tax_approved_at,
                review.effective_approved_at,
            )
        ):
            raise PriceBookConflict(
                "Price, tax, and effective date approvals are required first."
            )
        fields = {
            "price": ("price_approved_by_user_id", "price_approved_at"),
            "tax": ("tax_approved_by_user_id", "tax_approved_at"),
            "effective_date": (
                "effective_approved_by_user_id",
                "effective_approved_at",
            ),
            "activation_authorization": (
                "activation_authorized_by_user_id",
                "activation_authorized_at",
            ),
        }
        actor_field, time_field = fields[decision]
        setattr(review, actor_field, context.user.id)
        setattr(review, time_field, now)
        review.rationale = {**review.rationale, decision: reason}
        review.updated_at = now
        await session.flush()
        self._audit(
            session,
            context=context,
            entity_type="price_book_price_version",
            entity_id=version.id,
            action=f"{decision}_approved",
            state={"draft_version": version.version, "decision": decision},
            reason=reason,
            version=version.version,
        )
        return version

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

    async def create_review_batch(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: ReviewBatchCreate,
    ) -> PriceBookReviewBatch:
        codes = tuple(sorted(payload.service_codes))
        exclusions = tuple(sorted(payload.exclusions))
        if len(codes) != len(set(codes)) or len(exclusions) != len(set(exclusions)):
            raise PriceBookValidation("Review service selections must be unique.")
        if not set(exclusions).issubset(codes):
            raise PriceBookValidation(
                "Review exclusions must belong to the selected set."
            )
        async with session.begin():
            existing = await session.scalar(
                select(PriceBookReviewBatch).where(
                    PriceBookReviewBatch.company_id == context.company.id,
                    PriceBookReviewBatch.idempotency_key == payload.idempotency_key,
                )
            )
            if existing is not None:
                if (
                    existing.configuration_version != payload.configuration_version
                    or existing.review_type != payload.review_type
                    or tuple(existing.service_codes) != codes
                    or tuple(existing.exclusions) != exclusions
                    or existing.candidate_set_digest != payload.candidate_set_digest
                    or existing.selector != payload.selector
                ):
                    raise PriceBookConflict(
                        "Review idempotency key was used for different evidence."
                    )
                return existing
            batch = PriceBookReviewBatch(
                company_id=context.company.id,
                configuration_version=payload.configuration_version,
                review_type=payload.review_type,
                selector=payload.selector,
                service_codes=list(codes),
                exclusions=list(exclusions),
                candidate_set_digest=payload.candidate_set_digest,
                idempotency_key=payload.idempotency_key,
                created_by_user_id=context.user.id,
            )
            session.add(batch)
            await session.flush()
            self._audit(
                session,
                context=context,
                entity_type="price_book_review_batch",
                entity_id=batch.id,
                action="draft_created",
                state={"digest": batch.candidate_set_digest, "count": len(codes)},
                reason="Owner review batch saved as draft.",
                version=1,
            )
        return batch

    async def decide_review_batch(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        batch_id: UUID,
        payload: ReviewBatchDecision,
    ) -> PriceBookReviewBatch:
        async with session.begin():
            batch = await session.scalar(
                select(PriceBookReviewBatch)
                .where(
                    PriceBookReviewBatch.id == batch_id,
                    PriceBookReviewBatch.company_id == context.company.id,
                )
                .with_for_update()
            )
            if batch is None:
                raise PriceBookNotFound("Review batch was not found.")
            if (
                batch.version != payload.expected_version
                or batch.candidate_set_digest != payload.expected_digest
            ):
                raise PriceBookConflict("Review authority is stale.")
            if batch.status != "draft":
                if (
                    batch.status == payload.decision
                    and batch.decision_reason == payload.reason
                ):
                    return batch
                raise PriceBookConflict(
                    "Review batch already has a different decision."
                )
            batch.status = payload.decision
            batch.decision_reason = payload.reason
            batch.decided_by_user_id = context.user.id
            batch.decided_at = utc_now()
            batch.updated_at = batch.decided_at
            batch.version += 1
            self._audit(
                session,
                context=context,
                entity_type="price_book_review_batch",
                entity_id=batch.id,
                action=payload.decision,
                state={"digest": batch.candidate_set_digest, "status": batch.status},
                reason=payload.reason,
                version=batch.version,
            )
            BusinessEventService.stage(
                session,
                BusinessEventCreate(
                    event_type=EventType.PRICE_BOOK_REVIEW_BATCH_DECIDED,
                    entity_type="price_book_review_batch",
                    entity_id=batch.id,
                    company_id=context.company.id,
                    branch_id=None,
                    user_id=context.user.id,
                    payload={
                        "schema_version": "1.0",
                        "status": batch.status,
                        "candidate_set_digest": batch.candidate_set_digest,
                    },
                ),
            )
        return batch

    async def create_adjustment_proposal(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: AdjustmentProposalCreate,
    ) -> PriceBookAdjustmentProposal:
        codes = tuple(sorted(payload.affected_service_codes))
        exclusions = tuple(sorted(payload.owner_exclusions))
        if len(codes) != len(set(codes)) or not set(exclusions).issubset(codes):
            raise PriceBookValidation("Proposal service evidence is invalid.")
        async with session.begin():
            existing = await session.scalar(
                select(PriceBookAdjustmentProposal).where(
                    PriceBookAdjustmentProposal.company_id == context.company.id,
                    PriceBookAdjustmentProposal.recommendation_identity
                    == payload.recommendation_identity,
                )
            )
            if existing is not None:
                if existing.proposal_digest != payload.proposal_digest:
                    raise PriceBookConflict(
                        "Recommendation identity conflicts with existing evidence."
                    )
                return existing
            proposal = PriceBookAdjustmentProposal(
                company_id=context.company.id,
                source_price_book_version=payload.source_price_book_version,
                recommendation_identity=payload.recommendation_identity,
                economics_evidence_version=payload.economics_evidence_version,
                model_version=payload.model_version,
                affected_service_codes=list(codes),
                owner_exclusions=list(exclusions),
                transformation_kind=payload.transformation_kind,
                transformation=payload.transformation,
                impacts=list(payload.impacts),
                limitations=list(payload.limitations),
                effective_at=payload.effective_at,
                proposal_digest=payload.proposal_digest,
                created_by_user_id=context.user.id,
            )
            session.add(proposal)
            await session.flush()
            self._audit(
                session,
                context=context,
                entity_type="price_book_adjustment_proposal",
                entity_id=proposal.id,
                action="draft_created",
                state={"digest": proposal.proposal_digest, "count": len(codes)},
                reason="Non-activating successor proposal saved as draft.",
                version=1,
            )
        return proposal

    async def decide_adjustment_proposal(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        proposal_id: UUID,
        payload: AdjustmentProposalDecision,
    ) -> PriceBookAdjustmentProposal:
        async with session.begin():
            proposal = await session.scalar(
                select(PriceBookAdjustmentProposal)
                .where(
                    PriceBookAdjustmentProposal.id == proposal_id,
                    PriceBookAdjustmentProposal.company_id == context.company.id,
                )
                .with_for_update()
            )
            if proposal is None:
                raise PriceBookNotFound("Adjustment proposal was not found.")
            if (
                proposal.version != payload.expected_version
                or proposal.proposal_digest != payload.expected_digest
            ):
                raise PriceBookConflict("Adjustment proposal authority is stale.")
            if proposal.status != "draft":
                if proposal.status == payload.decision:
                    return proposal
                raise PriceBookConflict(
                    "Adjustment proposal already has a different decision."
                )
            proposal.status = payload.decision
            proposal.approved_by_user_id = (
                context.user.id if payload.decision == "approved" else None
            )
            proposal.approved_at = utc_now() if payload.decision == "approved" else None
            proposal.updated_at = utc_now()
            proposal.version += 1
            self._audit(
                session,
                context=context,
                entity_type="price_book_adjustment_proposal",
                entity_id=proposal.id,
                action=payload.decision,
                state={"digest": proposal.proposal_digest, "status": proposal.status},
                reason=payload.reason,
                version=proposal.version,
            )
            BusinessEventService.stage(
                session,
                BusinessEventCreate(
                    event_type=EventType.PRICE_BOOK_ADJUSTMENT_PROPOSAL_DECIDED,
                    entity_type="price_book_adjustment_proposal",
                    entity_id=proposal.id,
                    company_id=context.company.id,
                    branch_id=None,
                    user_id=context.user.id,
                    payload={
                        "schema_version": "1.0",
                        "status": proposal.status,
                        "proposal_digest": proposal.proposal_digest,
                    },
                ),
            )
        return proposal

    async def materialize_adjustment_proposal(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        proposal_id: UUID,
        payload: BulkMaterializeRequest,
    ) -> BulkMaterializeItem:
        """Create reviewable successor drafts from an approved proposal; never activate."""
        async with session.begin():
            proposal = await session.scalar(
                select(PriceBookAdjustmentProposal)
                .where(
                    PriceBookAdjustmentProposal.id == proposal_id,
                    PriceBookAdjustmentProposal.company_id == context.company.id,
                )
                .with_for_update()
            )
            if proposal is None:
                raise PriceBookNotFound("Adjustment proposal was not found.")
            if proposal.proposal_digest != payload.expected_digest:
                raise PriceBookConflict("Adjustment proposal digest is stale.")
            if proposal.materialization_key is not None:
                if proposal.materialization_key != payload.idempotency_key:
                    raise PriceBookConflict(
                        "Adjustment proposal was materialized by another command."
                    )
                return BulkMaterializeItem(
                    proposal_id=proposal.id,
                    proposal_digest=proposal.proposal_digest,
                    created_version_ids=tuple(
                        UUID(value) for value in proposal.materialized_version_ids
                    ),
                    created_count=len(proposal.materialized_version_ids),
                    replayed=True,
                )
            if (
                proposal.status != "approved"
                or proposal.version != payload.expected_version
            ):
                raise PriceBookConflict(
                    "Only the current approved proposal may create drafts."
                )
            if proposal.transformation_kind not in {"percentage", "fixed_amount"}:
                raise PriceBookValidation(
                    "This pricing transformation is not deterministically supported."
                )
            value_key = (
                "percentage"
                if proposal.transformation_kind == "percentage"
                else "fixed_amount"
            )
            try:
                transformation_value = Decimal(str(proposal.transformation[value_key]))
            except (InvalidOperation, KeyError) as error:
                raise PriceBookValidation(
                    "Adjustment transformation evidence is invalid."
                ) from error
            impact_by_code = {
                str(impact.get("service_code")): impact for impact in proposal.impacts
            }
            included = tuple(
                code
                for code in proposal.affected_service_codes
                if code not in set(proposal.owner_exclusions)
            )
            if set(impact_by_code) != set(included):
                raise PriceBookConflict("Adjustment impact set is incomplete or stale.")
            items = tuple(
                (
                    await session.scalars(
                        select(PriceBookServiceItem)
                        .where(
                            PriceBookServiceItem.company_id == context.company.id,
                            PriceBookServiceItem.code.in_(included),
                        )
                        .with_for_update()
                    )
                ).all()
            )
            if {item.code for item in items} != set(included):
                raise PriceBookConflict("Adjustment service set changed.")
            created: list[UUID] = []
            for item in sorted(items, key=lambda value: value.code):
                if item.current_version_id is None:
                    raise PriceBookConflict(
                        "Adjustment requires one active source price."
                    )
                source = await session.scalar(
                    select(PriceBookPriceVersion)
                    .where(
                        PriceBookPriceVersion.id == item.current_version_id,
                        PriceBookPriceVersion.company_id == context.company.id,
                        PriceBookPriceVersion.status == "active",
                    )
                    .with_for_update()
                )
                if source is None:
                    raise PriceBookConflict("Adjustment source price is not active.")
                impact = impact_by_code[item.code]
                if Decimal(str(impact.get("current_price"))) != source.unit_price:
                    raise PriceBookConflict("Adjustment source price changed.")
                proposed = Decimal(str(impact.get("proposed_price")))
                expected_proposed = (
                    source.unit_price
                    * (Decimal(1) + transformation_value / Decimal(100))
                    if proposal.transformation_kind == "percentage"
                    else source.unit_price + transformation_value
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if proposed != expected_proposed:
                    raise PriceBookConflict(
                        "Adjustment preview does not match its transformation."
                    )
                if proposed < 0:
                    raise PriceBookValidation("Proposed price cannot be negative.")
                revision = (
                    int(
                        await session.scalar(
                            select(func.max(PriceBookPriceVersion.revision)).where(
                                PriceBookPriceVersion.company_id == context.company.id,
                                PriceBookPriceVersion.service_item_id == item.id,
                            )
                        )
                        or 0
                    )
                    + 1
                )
                draft = PriceBookPriceVersion(
                    company_id=context.company.id,
                    service_item_id=item.id,
                    branch_id=source.branch_id,
                    tax_classification_id=source.tax_classification_id,
                    revision=revision,
                    currency=source.currency,
                    unit_price=proposed,
                    effective_at=proposal.effective_at,
                    expires_at=None,
                    created_by_user_id=context.user.id,
                )
                session.add(draft)
                await session.flush()
                components = tuple(
                    (
                        await session.scalars(
                            select(PriceBookComponent)
                            .where(
                                PriceBookComponent.company_id == context.company.id,
                                PriceBookComponent.price_version_id == source.id,
                            )
                            .order_by(PriceBookComponent.position)
                        )
                    ).all()
                )
                for component in components:
                    session.add(
                        PriceBookComponent(
                            company_id=context.company.id,
                            price_version_id=draft.id,
                            component_type=component.component_type,
                            code=component.code,
                            label=component.label,
                            quantity=component.quantity,
                            unit_cost=component.unit_cost,
                            position=component.position,
                        )
                    )
                created.append(draft.id)
                self._audit(
                    session,
                    context=context,
                    entity_type="price_book_price_version",
                    entity_id=draft.id,
                    action="bulk_successor_draft_created",
                    state={
                        "source_version_id": str(source.id),
                        "proposal_id": str(proposal.id),
                        "unit_price": str(proposed),
                    },
                    reason="Approved bulk proposal materialized as draft; not activated.",
                    version=1,
                )
            proposal.materialization_key = payload.idempotency_key
            proposal.materialized_version_ids = [str(value) for value in created]
            proposal.materialized_at = utc_now()
            proposal.updated_at = proposal.materialized_at
            self._audit(
                session,
                context=context,
                entity_type="price_book_adjustment_proposal",
                entity_id=proposal.id,
                action="materialized_as_drafts",
                state={
                    "count": len(created),
                    "proposal_digest": proposal.proposal_digest,
                },
                reason="Approved proposal created reviewable successor drafts only.",
                version=proposal.version,
            )
        return BulkMaterializeItem(
            proposal_id=proposal.id,
            proposal_digest=proposal.proposal_digest,
            created_version_ids=tuple(created),
            created_count=len(created),
            replayed=False,
        )


price_book_service = PriceBookService()

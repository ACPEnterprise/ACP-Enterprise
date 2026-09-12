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
    BulkDraftCreated,
    BulkDraftIssue,
    BulkDraftRequest,
    BulkDraftResult,
    BulkDraftRowValidation,
    BulkDraftValidation,
    BulkReviewUpdate,
    CatalogPage,
    CategoryCreate,
    CategoryItem,
    CategoryUpdate,
    ComponentItem,
    EffectiveCatalog,
    EffectiveOption,
    EffectiveServiceItem,
    OperatorCatalogPage,
    OperatorComponentItem,
    OperatorServiceItem,
    OptionCreate,
    OptionGroupCreate,
    OptionGroupItem,
    OptionItem,
    PriceVersionCreate,
    PriceVersionItem,
    PriceVersionUpdate,
    ReviewDecision,
    ReviewQueue,
    ReviewQueueRow,
    ServiceItem,
    ServiceItemCreate,
    ServiceItemUpdate,
    SnapshotRequest,
    TaxClassificationCreate,
    TaxClassificationItem,
    TaxClassificationUpdate,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PriceBookService:
    async def _bulk_draft_validation(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: BulkDraftRequest,
    ) -> BulkDraftValidation:
        categories = set(
            (
                await session.scalars(
                    select(PriceBookCategory.id).where(
                        PriceBookCategory.company_id == context.company.id,
                        PriceBookCategory.status == "active",
                    )
                )
            ).all()
        )
        taxes = set(
            (
                await session.scalars(
                    select(PriceBookTaxClassification.id).where(
                        PriceBookTaxClassification.company_id == context.company.id,
                        PriceBookTaxClassification.status == "active",
                    )
                )
            ).all()
        )
        existing = tuple(
            (
                await session.execute(
                    select(PriceBookServiceItem.code, PriceBookServiceItem.name).where(
                        PriceBookServiceItem.company_id == context.company.id
                    )
                )
            ).all()
        )
        existing_codes = {code.casefold() for code, _ in existing}
        existing_names = {name.strip().casefold() for _, name in existing}
        existing_source_identities = {
            source.strip().casefold()
            for state in (
                await session.scalars(
                    select(PriceBookAuditEntry.new_state).where(
                        PriceBookAuditEntry.company_id == context.company.id,
                        PriceBookAuditEntry.entity_type == "price_book_service_item",
                        PriceBookAuditEntry.action == "bulk_draft_created",
                    )
                )
            ).all()
            if isinstance((source := state.get("source_identity")), str)
            and source.strip()
        }
        request_codes: dict[str, int] = {}
        request_names: dict[str, int] = {}
        request_refs: dict[str, int] = {}
        request_sources: dict[str, int] = {}
        for row in payload.rows:
            request_codes[row.code.casefold()] = (
                request_codes.get(row.code.casefold(), 0) + 1
            )
            normalized_name = row.name.strip().casefold()
            request_names[normalized_name] = request_names.get(normalized_name, 0) + 1
            request_refs[row.client_ref] = request_refs.get(row.client_ref, 0) + 1
            if row.source_identity:
                source_key = row.source_identity.strip().casefold()
                request_sources[source_key] = request_sources.get(source_key, 0) + 1

        results: list[BulkDraftRowValidation] = []
        for row in payload.rows:
            issues: list[BulkDraftIssue] = []

            def issue(
                code: str,
                field: str,
                message: str,
                target: list[BulkDraftIssue] = issues,
            ) -> None:
                target.append(BulkDraftIssue(code=code, field=field, message=message))

            if request_refs[row.client_ref] > 1:
                issue(
                    "DUPLICATE_CLIENT_REFERENCE",
                    "client_ref",
                    "Row reference is duplicated in this batch.",
                )
            if row.source_identity is None or not row.source_identity.strip():
                issue(
                    "MISSING_SOURCE_IDENTITY",
                    "source_identity",
                    "Authoritative source identity evidence is required for readiness.",
                )
            else:
                source_key = row.source_identity.strip().casefold()
                if (
                    source_key in existing_source_identities
                    or request_sources[source_key] > 1
                ):
                    issue(
                        "DUPLICATE_SOURCE_IDENTITY",
                        "source_identity",
                        "Source identity already exists or is repeated in this batch.",
                    )
            if not row.code:
                issue("REQUIRED", "code", "Service code is required.")
            elif (
                row.code.casefold() in existing_codes
                or request_codes[row.code.casefold()] > 1
            ):
                issue(
                    "DUPLICATE_CODE",
                    "code",
                    "Service code already exists or is repeated in this batch.",
                )
            normalized_name = row.name.strip().casefold()
            if not normalized_name:
                issue("REQUIRED", "name", "Service name is required.")
            elif (
                normalized_name in existing_names or request_names[normalized_name] > 1
            ):
                issue(
                    "DUPLICATE_NAME",
                    "name",
                    "Service name already exists or is repeated in this batch.",
                )
            if row.category_id not in categories:
                issue(
                    "CATEGORY_UNAVAILABLE",
                    "category_id",
                    "Choose an active Price Book category.",
                )
            if (
                row.branch_id is not None
                and row.branch_id not in context.authorized_branch_ids
            ):
                issue("BRANCH_UNAVAILABLE", "branch_id", "Choose an authorized Branch.")
            if not row.customer_description.strip():
                issue(
                    "REQUIRED",
                    "customer_description",
                    "Customer description is required.",
                )
            if row.tax_classification_id not in taxes:
                issue(
                    "TAX_UNAVAILABLE",
                    "tax_classification_id",
                    "Choose an active tax classification.",
                )
            if row.unit_price is None:
                issue("REQUIRED", "unit_price", "Proposed sell price is required.")
            if row.effective_at is None:
                issue(
                    "REQUIRED", "effective_at", "Proposed effective date is required."
                )
            component_types = {component.component_type for component in row.components}
            if "labor" not in component_types:
                issue(
                    "MISSING_LABOR_INPUT",
                    "components",
                    "Labor quantity is not supplied.",
                )
            if "material" not in component_types:
                issue(
                    "MISSING_MATERIAL_INPUT",
                    "components",
                    "Material quantity is not supplied.",
                )
            if any(component.unit_cost is None for component in row.components):
                issue(
                    "MISSING_COST_AUTHORITY",
                    "components",
                    "One or more internal costs remain unavailable.",
                )
            fatal = {
                "DUPLICATE_CLIENT_REFERENCE",
                "DUPLICATE_CODE",
                "DUPLICATE_NAME",
                "DUPLICATE_SOURCE_IDENTITY",
                "REQUIRED",
                "CATEGORY_UNAVAILABLE",
                "BRANCH_UNAVAILABLE",
                "TAX_UNAVAILABLE",
            }
            can_save = not any(value.code in fatal for value in issues)
            results.append(
                BulkDraftRowValidation(
                    client_ref=row.client_ref,
                    can_save=can_save,
                    readiness="READY_FOR_REVIEW" if not issues else "INCOMPLETE",
                    issues=tuple(issues),
                )
            )
        return BulkDraftValidation(
            can_save=all(result.can_save for result in results), rows=tuple(results)
        )

    async def validate_bulk_drafts(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: BulkDraftRequest,
    ) -> BulkDraftValidation:
        return await self._bulk_draft_validation(
            session, context=context, payload=payload
        )

    async def create_bulk_drafts(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: BulkDraftRequest,
    ) -> BulkDraftResult:
        created: list[BulkDraftCreated] = []
        try:
            async with session.begin():
                validation = await self._bulk_draft_validation(
                    session, context=context, payload=payload
                )
                if not validation.can_save:
                    raise PriceBookValidation("Bulk draft rows require correction.")
                validations = {row.client_ref: row for row in validation.rows}
                now = utc_now()
                for row in payload.rows:
                    assert row.category_id is not None
                    assert row.tax_classification_id is not None
                    assert row.unit_price is not None
                    assert row.effective_at is not None
                    item = PriceBookServiceItem(
                        company_id=context.company.id,
                        branch_id=row.branch_id,
                        category_id=row.category_id,
                        code=row.code,
                        name=row.name.strip(),
                        customer_description=row.customer_description.strip(),
                        internal_description=row.internal_description,
                        created_by_user_id=context.user.id,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(item)
                    await session.flush()
                    version = PriceBookPriceVersion(
                        company_id=context.company.id,
                        service_item_id=item.id,
                        branch_id=row.branch_id,
                        tax_classification_id=row.tax_classification_id,
                        revision=1,
                        currency=row.currency,
                        unit_price=row.unit_price,
                        effective_at=row.effective_at,
                        created_by_user_id=context.user.id,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(version)
                    await session.flush()
                    components: list[PriceBookComponent] = []
                    for position, component in enumerate(row.components, 1):
                        record = PriceBookComponent(
                            company_id=context.company.id,
                            price_version_id=version.id,
                            component_type=component.component_type,
                            code=component.code,
                            label=component.label.strip(),
                            quantity=component.quantity,
                            unit_cost=component.unit_cost,
                            position=position,
                        )
                        session.add(record)
                        components.append(record)
                    await session.flush()
                    self._audit(
                        session,
                        context=context,
                        entity_type="price_book_service_item",
                        entity_id=item.id,
                        action="bulk_draft_created",
                        state={
                            "code": item.code,
                            "status": "draft",
                            "client_ref": row.client_ref,
                            "source_identity": row.source_identity,
                        },
                        reason="Operator bulk Price Book draft build.",
                        version=1,
                    )
                    self._audit(
                        session,
                        context=context,
                        entity_type="price_book_price_version",
                        entity_id=version.id,
                        action="draft_created",
                        state={
                            "revision": 1,
                            "status": "draft",
                            "unit_price": str(version.unit_price),
                            "currency": version.currency,
                        },
                        reason="Operator bulk Price Book draft build.",
                        version=1,
                    )
                    result = validations[row.client_ref]
                    created.append(
                        BulkDraftCreated(
                            client_ref=row.client_ref,
                            service_item=ServiceItem.model_validate(item),
                            draft_version=PriceVersionItem.model_validate(
                                version
                            ).model_copy(
                                update={
                                    "components": tuple(
                                        ComponentItem.model_validate(value)
                                        for value in components
                                    )
                                }
                            ),
                            readiness=result.readiness,
                            issues=result.issues,
                        )
                    )
        except IntegrityError as error:
            raise PriceBookConflict(
                "Bulk draft identity conflicts with current authority."
            ) from error
        return BulkDraftResult(created=tuple(created))

    async def review_queue(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        branch_id: UUID | None = None,
        category_id: UUID | None = None,
        classification: str | None = None,
        search: str | None = None,
    ) -> ReviewQueue:
        """Return management-only, derived readiness for native draft versions."""
        if branch_id is not None and branch_id not in context.authorized_branch_ids:
            raise PriceBookNotFound("Branch was not found.")
        query = (
            select(PriceBookPriceVersion, PriceBookServiceItem)
            .join(
                PriceBookServiceItem,
                and_(
                    PriceBookServiceItem.company_id == PriceBookPriceVersion.company_id,
                    PriceBookServiceItem.id == PriceBookPriceVersion.service_item_id,
                ),
            )
            .where(
                PriceBookPriceVersion.company_id == context.company.id,
                PriceBookPriceVersion.status == "draft",
                PriceBookServiceItem.status == "draft",
            )
        )
        if branch_id is not None:
            query = query.where(
                or_(
                    PriceBookPriceVersion.branch_id.is_(None),
                    PriceBookPriceVersion.branch_id == branch_id,
                )
            )
        if category_id is not None:
            query = query.where(PriceBookServiceItem.category_id == category_id)
        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.where(
                or_(
                    PriceBookServiceItem.code.ilike(term),
                    PriceBookServiceItem.name.ilike(term),
                    PriceBookServiceItem.customer_description.ilike(term),
                )
            )
        pairs = tuple((await session.execute(query)).all())
        if not pairs:
            return ReviewQueue(rows=())

        items = {item.id: item for _, item in pairs}
        versions = {version.id: version for version, _ in pairs}
        all_identities = tuple(
            (
                await session.execute(
                    select(PriceBookServiceItem.code, PriceBookServiceItem.name).where(
                        PriceBookServiceItem.company_id == context.company.id
                    )
                )
            ).all()
        )
        code_counts: dict[str, int] = {}
        name_counts: dict[str, int] = {}
        for code, name in all_identities:
            code_key = code.strip().casefold()
            name_key = name.strip().casefold()
            code_counts[code_key] = code_counts.get(code_key, 0) + 1
            name_counts[name_key] = name_counts.get(name_key, 0) + 1
        categories = {
            row.id: row
            for row in (
                await session.scalars(
                    select(PriceBookCategory).where(
                        PriceBookCategory.company_id == context.company.id,
                        PriceBookCategory.id.in_(
                            {item.category_id for item in items.values()}
                        ),
                    )
                )
            ).all()
        }
        taxes = {
            row.id: row
            for row in (
                await session.scalars(
                    select(PriceBookTaxClassification).where(
                        PriceBookTaxClassification.company_id == context.company.id,
                        PriceBookTaxClassification.id.in_(
                            {
                                version.tax_classification_id
                                for version in versions.values()
                            }
                        ),
                    )
                )
            ).all()
        }
        branch_ids = {
            value
            for version in versions.values()
            if (value := version.branch_id) is not None
        }
        branches = (
            {
                row.id: row
                for row in (
                    await session.scalars(
                        select(Branch).where(
                            Branch.company_id == context.company.id,
                            Branch.id.in_(branch_ids),
                        )
                    )
                ).all()
            }
            if branch_ids
            else {}
        )
        components = tuple(
            (
                await session.scalars(
                    select(PriceBookComponent).where(
                        PriceBookComponent.company_id == context.company.id,
                        PriceBookComponent.price_version_id.in_(versions),
                    )
                )
            ).all()
        )
        by_version: dict[UUID, list[PriceBookComponent]] = {}
        for component in components:
            by_version.setdefault(component.price_version_id, []).append(component)

        audits = tuple(
            (
                await session.scalars(
                    select(PriceBookAuditEntry)
                    .where(
                        PriceBookAuditEntry.company_id == context.company.id,
                        or_(
                            and_(
                                PriceBookAuditEntry.entity_type
                                == "price_book_service_item",
                                PriceBookAuditEntry.entity_id.in_(items),
                                PriceBookAuditEntry.action == "bulk_draft_created",
                            ),
                            and_(
                                PriceBookAuditEntry.entity_type
                                == "price_book_price_version",
                                PriceBookAuditEntry.entity_id.in_(versions),
                                PriceBookAuditEntry.action.in_(
                                    (
                                        "review_completed",
                                        "review_returned",
                                        "review_metadata_updated",
                                        "individual_review_requested",
                                    )
                                ),
                            ),
                        ),
                    )
                    .order_by(PriceBookAuditEntry.occurred_at, PriceBookAuditEntry.id)
                )
            ).all()
        )
        source_by_item: dict[UUID, str] = {}
        review_by_version: dict[UUID, str] = {}
        for audit in audits:
            if audit.entity_type == "price_book_service_item":
                source = audit.new_state.get("source_identity")
                if isinstance(source, str) and source.strip():
                    source_by_item[audit.entity_id] = source.strip()
            else:
                review_by_version[audit.entity_id] = audit.action
        source_counts: dict[str, int] = {}
        for source in source_by_item.values():
            source_counts[source] = source_counts.get(source, 0) + 1

        rows: list[ReviewQueueRow] = []
        for version, item in pairs:
            missing: list[str] = []
            conflicts: list[str] = []
            category = categories.get(item.category_id)
            tax = taxes.get(version.tax_classification_id)
            branch = branches.get(version.branch_id) if version.branch_id else None
            source = source_by_item.get(item.id)
            record_components = by_version.get(version.id, [])
            typed = {
                kind: [
                    value for value in record_components if value.component_type == kind
                ]
                for kind in ("labor", "material")
            }
            if source is None:
                missing.append("Missing source identity evidence.")
            elif source_counts[source] > 1:
                conflicts.append("Source identity is bound to more than one draft.")
            if code_counts[item.code.strip().casefold()] > 1:
                conflicts.append("Service code duplicates another native item.")
            if name_counts[item.name.strip().casefold()] > 1:
                conflicts.append("Service name duplicates another native item.")
            if category is None or category.status != "active":
                missing.append("Choose an active category.")
            if version.branch_id is not None and (
                branch is None
                or branch.status != "active"
                or branch.id not in context.authorized_branch_ids
            ):
                missing.append("Choose an authorized active Branch.")
            if tax is None or tax.status != "active":
                missing.append("Choose an active tax classification.")
            if not typed["labor"]:
                missing.append(
                    "Labor quantity is required; it was not assumed to be zero."
                )
            if not typed["material"]:
                missing.append(
                    "Material quantity is required; it was not assumed to be zero."
                )
            if any(value.unit_cost is None for value in record_components):
                missing.append(
                    "Internal cost evidence is incomplete; it was not assumed to be zero."
                )
            review_complete = review_by_version.get(version.id) == "review_completed"
            if conflicts:
                candidate_state = "CONFLICTING"
            elif missing:
                candidate_state = "INCOMPLETE"
            elif review_complete:
                candidate_state = "READY_FOR_REVIEW"
            else:
                candidate_state = "DRAFT_CANDIDATE"
            if missing or conflicts:
                activation_readiness = "NOT_READY"
            elif review_complete:
                activation_readiness = "READY_FOR_ACTIVATION"
            else:
                activation_readiness = "READY_FOR_REVIEW"

            def quantity(
                kind: str,
                component_types: dict[str, list[PriceBookComponent]] = typed,
            ) -> Decimal | None:
                values = component_types[kind]
                return (
                    sum((value.quantity for value in values), Decimal(0))
                    if values
                    else None
                )

            def cost(
                kind: str,
                component_types: dict[str, list[PriceBookComponent]] = typed,
            ) -> Decimal | None:
                values = component_types[kind]
                if not values or any(value.unit_cost is None for value in values):
                    return None
                return sum(
                    (
                        value.quantity * value.unit_cost
                        for value in values
                        if value.unit_cost is not None
                    ),
                    Decimal(0),
                )

            row = ReviewQueueRow(
                service_item_id=item.id,
                price_version_id=version.id,
                item_version=item.version,
                price_version=version.version,
                code=item.code,
                name=item.name,
                customer_description=item.customer_description,
                category_name=category.name if category else None,
                branch_name=branch.name if branch else "Company-wide",
                proposed_price=version.unit_price,
                currency=version.currency,
                effective_at=version.effective_at,
                tax_classification_name=tax.name if tax else None,
                labor_quantity=quantity("labor"),
                material_quantity=quantity("material"),
                labor_cost=cost("labor"),
                material_cost=cost("material"),
                source_identity=source,
                candidate_state=candidate_state,
                activation_readiness=activation_readiness,
                missing_evidence_reasons=tuple(missing),
                conflict_reasons=tuple(conflicts),
                management_review_complete=review_complete,
            )
            if classification is None or classification in (
                row.candidate_state,
                row.activation_readiness,
            ):
                rows.append(row)
        rows.sort(
            key=lambda value: (value.category_name or "", value.branch_name, value.code)
        )
        return ReviewQueue(rows=tuple(rows))

    async def bulk_review_update(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        payload: BulkReviewUpdate,
    ) -> ReviewQueue:
        if not any(
            (
                payload.category_id,
                payload.branch_id,
                payload.tax_classification_id,
                payload.effective_at,
                payload.mark_for_individual_review,
            )
        ):
            raise PriceBookValidation("Choose at least one review metadata change.")
        target_item_ids = {target.service_item_id for target in payload.targets}
        target_version_ids = {target.price_version_id for target in payload.targets}
        if len(target_item_ids) != len(payload.targets) or len(
            target_version_ids
        ) != len(payload.targets):
            raise PriceBookValidation("Each review target must be unique.")
        async with session.begin():
            items = {
                item.id: item
                for item in (
                    await session.scalars(
                        select(PriceBookServiceItem)
                        .where(
                            PriceBookServiceItem.company_id == context.company.id,
                            PriceBookServiceItem.id.in_(target_item_ids),
                        )
                        .with_for_update()
                    )
                ).all()
            }
            versions = {
                version.id: version
                for version in (
                    await session.scalars(
                        select(PriceBookPriceVersion)
                        .where(
                            PriceBookPriceVersion.company_id == context.company.id,
                            PriceBookPriceVersion.id.in_(target_version_ids),
                        )
                        .with_for_update()
                    )
                ).all()
            }
            if len(items) != len(payload.targets) or len(versions) != len(
                payload.targets
            ):
                raise PriceBookNotFound("One or more review rows were not found.")
            if payload.category_id is not None and not await session.scalar(
                select(PriceBookCategory.id).where(
                    PriceBookCategory.id == payload.category_id,
                    PriceBookCategory.company_id == context.company.id,
                    PriceBookCategory.status == "active",
                )
            ):
                raise PriceBookNotFound("Category was not found.")
            if payload.tax_classification_id is not None and not await session.scalar(
                select(PriceBookTaxClassification.id).where(
                    PriceBookTaxClassification.id == payload.tax_classification_id,
                    PriceBookTaxClassification.company_id == context.company.id,
                    PriceBookTaxClassification.status == "active",
                )
            ):
                raise PriceBookNotFound("Tax classification was not found.")
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
            now = utc_now()
            for target in payload.targets:
                item = items[target.service_item_id]
                version = versions[target.price_version_id]
                if (
                    version.service_item_id != item.id
                    or item.status != "draft"
                    or version.status != "draft"
                ):
                    raise PriceBookConflict(
                        "Only matching draft rows may be bulk reviewed."
                    )
                if (
                    item.version != target.expected_item_version
                    or version.version != target.expected_price_version
                ):
                    raise PriceBookConflict("A review row changed before this update.")
                prior: dict[str, object] = {
                    "category_id": str(item.category_id),
                    "branch_id": str(version.branch_id) if version.branch_id else None,
                    "tax_classification_id": str(version.tax_classification_id),
                    "effective_at": version.effective_at.isoformat(),
                }
                if payload.category_id is not None:
                    item.category_id = payload.category_id
                if payload.branch_id is not None:
                    item.branch_id = payload.branch_id
                    version.branch_id = payload.branch_id
                if payload.tax_classification_id is not None:
                    version.tax_classification_id = payload.tax_classification_id
                if payload.effective_at is not None:
                    version.effective_at = payload.effective_at
                item.version += 1
                version.version += 1
                item.updated_at = now
                version.updated_at = now
                self._audit(
                    session,
                    context=context,
                    entity_type="price_book_price_version",
                    entity_id=version.id,
                    action="individual_review_requested"
                    if payload.mark_for_individual_review
                    else "review_metadata_updated",
                    prior_state=prior,
                    state={
                        "category_id": str(item.category_id),
                        "branch_id": str(version.branch_id)
                        if version.branch_id
                        else None,
                        "tax_classification_id": str(version.tax_classification_id),
                        "effective_at": version.effective_at.isoformat(),
                        "activation_status": "NOT_ACTIVATED",
                    },
                    reason=payload.reason,
                    version=version.version,
                )
        return await self.review_queue(session, context=context)

    async def record_review_decision(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        version_id: UUID,
        payload: ReviewDecision,
    ) -> ReviewQueueRow:
        async with session.begin():
            before = await self.review_queue(session, context=context)
            before_row = next(
                (
                    value
                    for value in before.rows
                    if value.price_version_id == version_id
                ),
                None,
            )
            if before_row is None:
                raise PriceBookNotFound("Draft version was not found.")
            if (
                payload.decision == "REVIEW_COMPLETE"
                and before_row.activation_readiness != "READY_FOR_REVIEW"
            ):
                raise PriceBookValidation(
                    "Mandatory evidence is incomplete; review cannot make this draft activation-ready."
                )
            version = await session.scalar(
                select(PriceBookPriceVersion)
                .where(
                    PriceBookPriceVersion.id == version_id,
                    PriceBookPriceVersion.company_id == context.company.id,
                )
                .with_for_update()
            )
            if version is None:
                raise PriceBookNotFound("Draft version was not found.")
            if version.status != "draft":
                raise PriceBookConflict("Only a draft can receive a review decision.")
            if version.version != payload.expected_price_version:
                raise PriceBookConflict("Draft changed before this review decision.")
            version.version += 1
            version.updated_at = utc_now()
            self._audit(
                session,
                context=context,
                entity_type="price_book_price_version",
                entity_id=version.id,
                action="review_completed"
                if payload.decision == "REVIEW_COMPLETE"
                else "review_returned",
                state={
                    "decision": payload.decision,
                    "activation_status": "NOT_ACTIVATED",
                },
                reason=payload.reason,
                version=version.version,
            )
        queue = await self.review_queue(session, context=context)
        row = next(
            (value for value in queue.rows if value.price_version_id == version_id),
            None,
        )
        if row is None:
            raise PriceBookNotFound("Reviewed draft was not found.")
        return row

    async def effective_catalog(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        branch_id: UUID,
        effective_at: datetime,
        category_id: UUID | None = None,
        search: str | None = None,
    ) -> EffectiveCatalog:
        """Resolve the customer-safe catalog at one authoritative point in time."""
        if branch_id not in context.authorized_branch_ids:
            raise PriceBookNotFound("Branch was not found.")
        item_query = select(PriceBookServiceItem).where(
            PriceBookServiceItem.company_id == context.company.id,
            PriceBookServiceItem.status == "active",
            or_(
                PriceBookServiceItem.branch_id.is_(None),
                PriceBookServiceItem.branch_id == branch_id,
            ),
        )
        if category_id is not None:
            item_query = item_query.where(
                PriceBookServiceItem.category_id == category_id
            )
        if search and search.strip():
            term = f"%{search.strip()}%"
            item_query = item_query.where(
                or_(
                    PriceBookServiceItem.name.ilike(term),
                    PriceBookServiceItem.code.ilike(term),
                    PriceBookServiceItem.customer_description.ilike(term),
                )
            )
        items = tuple(
            (
                await session.scalars(item_query.order_by(PriceBookServiceItem.name))
            ).all()
        )
        if not items:
            return EffectiveCatalog(effective_at=effective_at, items=())

        item_ids = tuple(item.id for item in items)
        versions = tuple(
            (
                await session.scalars(
                    select(PriceBookPriceVersion).where(
                        PriceBookPriceVersion.company_id == context.company.id,
                        PriceBookPriceVersion.service_item_id.in_(item_ids),
                        PriceBookPriceVersion.status == "active",
                        PriceBookPriceVersion.effective_at <= effective_at,
                        or_(
                            PriceBookPriceVersion.expires_at.is_(None),
                            PriceBookPriceVersion.expires_at > effective_at,
                        ),
                        or_(
                            PriceBookPriceVersion.branch_id.is_(None),
                            PriceBookPriceVersion.branch_id == branch_id,
                        ),
                    )
                )
            ).all()
        )
        versions_by_item: dict[UUID, list[PriceBookPriceVersion]] = {}
        for version in versions:
            versions_by_item.setdefault(version.service_item_id, []).append(version)

        categories = {
            row.id: row
            for row in (
                await session.scalars(
                    select(PriceBookCategory).where(
                        PriceBookCategory.company_id == context.company.id,
                        PriceBookCategory.status == "active",
                    )
                )
            ).all()
        }
        taxes = {
            row.id: row
            for row in (
                await session.scalars(
                    select(PriceBookTaxClassification).where(
                        PriceBookTaxClassification.company_id == context.company.id,
                        PriceBookTaxClassification.status == "active",
                    )
                )
            ).all()
        }
        option_rows = tuple(
            (
                await session.execute(
                    select(PriceBookOption, PriceBookOptionGroup)
                    .join(
                        PriceBookOptionGroup,
                        PriceBookOptionGroup.id == PriceBookOption.option_group_id,
                    )
                    .where(
                        PriceBookOption.company_id == context.company.id,
                        PriceBookOption.service_item_id.in_(item_ids),
                        PriceBookOptionGroup.company_id == context.company.id,
                        PriceBookOptionGroup.status == "active",
                    )
                    .order_by(PriceBookOption.position)
                )
            ).all()
        )
        options_by_item: dict[UUID, list[EffectiveOption]] = {}
        for option, group in option_rows:
            options_by_item.setdefault(option.service_item_id, []).append(
                EffectiveOption(
                    group_id=group.id,
                    group_name=group.name,
                    minimum_selections=group.minimum_selections,
                    maximum_selections=group.maximum_selections,
                    option_id=option.id,
                    option_label=option.label,
                )
            )

        resolved: list[EffectiveServiceItem] = []
        for item in items:
            candidates = versions_by_item.get(item.id, [])
            scoped = [row for row in candidates if row.branch_id == branch_id] or [
                row for row in candidates if row.branch_id is None
            ]
            # Ambiguous authority is omitted and will still fail closed at snapshot time.
            if len(scoped) != 1:
                continue
            version = scoped[0]
            category = categories.get(item.category_id)
            tax = taxes.get(version.tax_classification_id)
            if category is None or tax is None:
                continue
            resolved.append(
                EffectiveServiceItem(
                    item_id=item.id,
                    item_code=item.code,
                    item_name=item.name,
                    customer_description=item.customer_description,
                    category_id=category.id,
                    category_name=category.name,
                    price_version_id=version.id,
                    unit_price=version.unit_price,
                    currency=version.currency,
                    effective_at=version.effective_at,
                    expires_at=version.expires_at,
                    tax_classification_name=tax.name,
                    taxable=tax.taxable,
                    options=tuple(options_by_item.get(item.id, [])),
                )
            )
        return EffectiveCatalog(effective_at=effective_at, items=tuple(resolved))

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

    async def operator_catalog(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        branch_id: UUID | None = None,
    ) -> OperatorCatalogPage:
        public = await self.catalog(session, context=context, branch_id=branch_id)
        categories = tuple(
            (
                await session.scalars(
                    select(PriceBookCategory)
                    .where(PriceBookCategory.company_id == context.company.id)
                    .order_by(PriceBookCategory.name)
                )
            ).all()
        )
        taxes = tuple(
            (
                await session.scalars(
                    select(PriceBookTaxClassification)
                    .where(PriceBookTaxClassification.company_id == context.company.id)
                    .order_by(PriceBookTaxClassification.name)
                )
            ).all()
        )
        version_ids = [version.id for version in public.versions]
        components = (
            tuple(
                (
                    await session.scalars(
                        select(PriceBookComponent)
                        .where(
                            PriceBookComponent.company_id == context.company.id,
                            PriceBookComponent.price_version_id.in_(version_ids),
                        )
                        .order_by(
                            PriceBookComponent.price_version_id,
                            PriceBookComponent.position,
                        )
                    )
                ).all()
            )
            if version_ids
            else ()
        )
        return OperatorCatalogPage(
            categories=tuple(
                CategoryItem.model_validate(value) for value in categories
            ),
            tax_classifications=tuple(
                TaxClassificationItem.model_validate(value) for value in taxes
            ),
            service_items=tuple(
                OperatorServiceItem.model_validate(item)
                for item in (
                    (
                        await session.scalars(
                            select(PriceBookServiceItem)
                            .where(
                                PriceBookServiceItem.company_id == context.company.id,
                                PriceBookServiceItem.id.in_(
                                    [value.id for value in public.service_items]
                                ),
                            )
                            .order_by(PriceBookServiceItem.name)
                        )
                    ).all()
                    if public.service_items
                    else ()
                )
            ),
            versions=public.versions,
            option_groups=public.option_groups,
            options=public.options,
            internal_components=tuple(
                OperatorComponentItem.model_validate(component)
                for component in components
            ),
        )

    async def update_category(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        category_id: UUID,
        payload: CategoryUpdate,
    ) -> PriceBookCategory:
        now = utc_now()
        async with session.begin():
            category = await session.scalar(
                select(PriceBookCategory)
                .where(
                    PriceBookCategory.id == category_id,
                    PriceBookCategory.company_id == context.company.id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if category is None:
                raise PriceBookNotFound("Category was not found.")
            if category.version != payload.expected_version:
                raise PriceBookConflict("Category changed before this update.")
            if payload.parent_id == category.id:
                raise PriceBookValidation("A category cannot be its own parent.")
            if payload.parent_id and not await session.scalar(
                select(PriceBookCategory.id).where(
                    PriceBookCategory.id == payload.parent_id,
                    PriceBookCategory.company_id == context.company.id,
                    PriceBookCategory.status == "active",
                )
            ):
                raise PriceBookNotFound("Parent category was not found.")
            if payload.status == "archived" and await session.scalar(
                select(PriceBookServiceItem.id).where(
                    PriceBookServiceItem.company_id == context.company.id,
                    PriceBookServiceItem.category_id == category.id,
                    PriceBookServiceItem.status.in_(("draft", "active")),
                )
            ):
                raise PriceBookConflict(
                    "Active or draft items still use this category."
                )
            if payload.status == "archived" and await session.scalar(
                select(PriceBookCategory.id).where(
                    PriceBookCategory.company_id == context.company.id,
                    PriceBookCategory.parent_id == category.id,
                    PriceBookCategory.status == "active",
                )
            ):
                raise PriceBookConflict(
                    "Active child categories still use this category."
                )
            prior: dict[str, object] = {
                "name": category.name,
                "description": category.description,
                "parent_id": str(category.parent_id) if category.parent_id else None,
                "status": category.status,
            }
            category.name = payload.name.strip()
            category.description = payload.description
            category.parent_id = payload.parent_id
            category.status = payload.status
            category.version += 1
            category.updated_at = now
            self._audit(
                session,
                context=context,
                entity_type="price_book_category",
                entity_id=category.id,
                action="updated" if payload.status == "active" else "archived",
                prior_state=prior,
                state={
                    "name": category.name,
                    "parent_id": str(category.parent_id)
                    if category.parent_id
                    else None,
                    "status": category.status,
                },
                reason="Operator updated Price Book category.",
                version=category.version,
            )
        return category

    async def update_item(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        item_id: UUID,
        payload: ServiceItemUpdate,
    ) -> PriceBookServiceItem:
        now = utc_now()
        async with session.begin():
            item = await session.scalar(
                select(PriceBookServiceItem)
                .where(
                    PriceBookServiceItem.id == item_id,
                    PriceBookServiceItem.company_id == context.company.id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if item is None:
                raise PriceBookNotFound("Service item was not found.")
            if item.version != payload.expected_version:
                raise PriceBookConflict("Service item changed before this update.")
            if not await session.scalar(
                select(PriceBookCategory.id).where(
                    PriceBookCategory.id == payload.category_id,
                    PriceBookCategory.company_id == context.company.id,
                    PriceBookCategory.status == "active",
                )
            ):
                raise PriceBookNotFound("Category was not found.")
            prior: dict[str, object] = {
                "category_id": str(item.category_id),
                "name": item.name,
                "customer_description": item.customer_description,
                "internal_description": item.internal_description,
            }
            item.category_id = payload.category_id
            item.name = payload.name.strip()
            item.customer_description = payload.customer_description.strip()
            item.internal_description = payload.internal_description
            item.version += 1
            item.updated_at = now
            self._audit(
                session,
                context=context,
                entity_type="price_book_service_item",
                entity_id=item.id,
                action="updated",
                prior_state=prior,
                state={
                    "category_id": str(item.category_id),
                    "name": item.name,
                    "customer_description": item.customer_description,
                },
                reason="Operator updated Price Book service item.",
                version=item.version,
            )
        return item

    async def update_tax(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        tax_id: UUID,
        payload: TaxClassificationUpdate,
    ) -> PriceBookTaxClassification:
        now = utc_now()
        async with session.begin():
            record = await session.scalar(
                select(PriceBookTaxClassification)
                .where(
                    PriceBookTaxClassification.id == tax_id,
                    PriceBookTaxClassification.company_id == context.company.id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if record is None:
                raise PriceBookNotFound("Tax classification was not found.")
            if record.version != payload.expected_version:
                raise PriceBookConflict(
                    "Tax classification changed before this update."
                )
            prior: dict[str, object] = {
                "name": record.name,
                "taxable": record.taxable,
                "status": record.status,
            }
            record.name = payload.name.strip()
            record.taxable = payload.taxable
            record.status = payload.status
            record.version += 1
            record.updated_at = now
            self._audit(
                session,
                context=context,
                entity_type="price_book_tax_classification",
                entity_id=record.id,
                action="updated",
                prior_state=prior,
                state={
                    "name": record.name,
                    "taxable": record.taxable,
                    "status": record.status,
                },
                reason="Operator updated Price Book tax classification.",
                version=record.version,
            )
        return record

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
                "option_group_name": selected_option_group.name
                if selected_option_group
                else None,
                "option_id": str(selected_option.id) if selected_option else None,
                "option_label": selected_option.label if selected_option else None,
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

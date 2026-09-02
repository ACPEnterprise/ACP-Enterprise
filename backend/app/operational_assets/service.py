import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer, ServiceLocation
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.inventory.models import StockLocation
from app.jobs.models import Job
from app.operational_assets.models import (
    Asset,
    AssetActionEvidence,
    AssetEvidence,
    AssetLifecycleEvidence,
    AssetRelationship,
)
from app.operational_assets.schemas import (
    AssetActionCreate,
    AssetCreate,
    EvidenceCreate,
    LifecycleChange,
    RelationshipCreate,
)
from app.platform.branch.models import Branch
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext


class AssetError(Exception):
    pass


class AssetNotFound(AssetError):
    pass


class AssetConflict(AssetError):
    pass


class AssetValidation(AssetError):
    pass


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


class AssetService:
    @staticmethod
    def _scope(context: AuthorizationContext, branch_id: UUID) -> None:
        if not context.can_access_branch(branch_id):
            raise AssetNotFound()

    @staticmethod
    async def _asset(
        session: AsyncSession,
        context: AuthorizationContext,
        asset_id: UUID,
        *,
        lock: bool = False,
    ) -> Asset:
        query = select(Asset).where(
            Asset.id == asset_id,
            Asset.company_id == context.company.id,
            Asset.branch_id.in_(context.authorized_branch_ids),
        )
        if lock:
            query = query.with_for_update()
        row = await session.scalar(query)
        if row is None:
            raise AssetNotFound()
        return row

    async def list_assets(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        *,
        branch_id: UUID | None,
        asset_class: str | None,
        lifecycle: str | None,
        query: str | None,
        limit: int,
    ) -> list[Asset]:
        branches = (branch_id,) if branch_id else tuple(context.authorized_branch_ids)
        if branch_id:
            self._scope(context, branch_id)
        stmt = select(Asset).where(
            Asset.company_id == context.company.id, Asset.branch_id.in_(branches)
        )
        if asset_class:
            stmt = stmt.where(Asset.asset_class == asset_class)
        if lifecycle:
            stmt = stmt.where(Asset.lifecycle == lifecycle)
        if query:
            term = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(Asset.asset_number.ilike(term), Asset.display_name.ilike(term))
            )
        return list(
            (
                await session.scalars(
                    stmt.order_by(Asset.asset_number, Asset.id).limit(limit)
                )
            ).all()
        )

    async def create(
        self, session: AsyncSession, context: AuthorizationContext, data: AssetCreate
    ) -> Asset:
        self._scope(context, data.branch_id)
        raw = data.model_dump(mode="json", exclude={"idempotency_key"})
        request = digest(raw)
        replay = await session.scalar(
            select(Asset).where(
                Asset.company_id == context.company.id,
                Asset.idempotency_key == data.idempotency_key,
            )
        )
        if replay:
            if replay.request_digest != request:
                raise AssetConflict()
            return replay
        if data.predecessor_asset_id:
            predecessor = await self._asset(
                session, context, data.predecessor_asset_id, lock=True
            )
            if predecessor.asset_class != data.asset_class:
                raise AssetValidation()
        row = Asset(
            company_id=context.company.id,
            branch_id=data.branch_id,
            asset_number=data.asset_number.strip().upper(),
            asset_class=data.asset_class,
            display_name=data.display_name.strip(),
            predecessor_asset_id=data.predecessor_asset_id,
            provenance=data.provenance,
            identity_digest=digest({"company": context.company.id, **raw}),
            request_digest=request,
            idempotency_key=data.idempotency_key,
            created_by_user_id=context.user.id,
        )
        session.add(row)
        await session.flush()
        self._event(
            session,
            row,
            context.user.id,
            EventType.ASSET_CREATED,
            "created",
            row.identity_digest,
        )
        await session.commit()
        await session.refresh(row)
        return row

    async def detail(
        self, session: AsyncSession, context: AuthorizationContext, asset_id: UUID
    ):
        row = await self._asset(session, context, asset_id)
        evidence = list(
            (
                await session.scalars(
                    select(AssetEvidence)
                    .where(
                        AssetEvidence.company_id == context.company.id,
                        AssetEvidence.asset_id == row.id,
                    )
                    .order_by(AssetEvidence.occurred_at.desc(), AssetEvidence.id)
                )
            ).all()
        )
        relationships = list(
            (
                await session.scalars(
                    select(AssetRelationship)
                    .where(
                        AssetRelationship.company_id == context.company.id,
                        AssetRelationship.asset_id == row.id,
                    )
                    .order_by(AssetRelationship.valid_from.desc(), AssetRelationship.id)
                )
            ).all()
        )
        readiness, reasons = self.readiness(row, evidence)
        return row, evidence, relationships, readiness, reasons

    async def add_evidence(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        asset_id: UUID,
        data: EvidenceCreate,
    ) -> AssetEvidence:
        row = await self._asset(session, context, asset_id, lock=True)
        await self._validate_evidence(session, row, data)
        raw = data.model_dump(mode="json", exclude={"idempotency_key"})
        request = digest(raw)
        replay = await session.scalar(
            select(AssetEvidence).where(
                AssetEvidence.company_id == context.company.id,
                AssetEvidence.idempotency_key == data.idempotency_key,
            )
        )
        if replay:
            if replay.asset_id != row.id or replay.request_digest != request:
                raise AssetConflict()
            return replay
        evidence_digest = digest({"asset": row.identity_digest, **raw})
        duplicate = await session.scalar(
            select(AssetEvidence).where(
                AssetEvidence.company_id == context.company.id,
                AssetEvidence.asset_id == row.id,
                AssetEvidence.evidence_digest == evidence_digest,
            )
        )
        if duplicate:
            return duplicate
        item = AssetEvidence(
            company_id=context.company.id,
            branch_id=row.branch_id,
            asset_id=row.id,
            evidence_type=data.evidence_type,
            state=data.state,
            value=data.value,
            source_reference=data.source_reference,
            protected_document_id=data.protected_document_id,
            occurred_at=data.occurred_at,
            evidence_digest=evidence_digest,
            request_digest=request,
            idempotency_key=data.idempotency_key,
            actor_user_id=context.user.id,
        )
        session.add(item)
        await session.flush()
        self._event(
            session,
            row,
            context.user.id,
            EventType.ASSET_EVIDENCE_RECORDED,
            data.evidence_type,
            evidence_digest,
        )
        await session.commit()
        await session.refresh(item)
        return item

    async def _validate_evidence(
        self, session: AsyncSession, asset: Asset, data: EvidenceCreate
    ) -> None:
        if data.evidence_type == "powertrain":
            if asset.asset_class != "vehicle":
                raise AssetValidation()
            powertrain = str(data.value.get("type", "")).upper()
            if powertrain not in {
                "GASOLINE",
                "DIESEL",
                "ELECTRIC",
                "HYBRID",
                "OTHER",
                "UNKNOWN",
            }:
                raise AssetValidation()
        if data.evidence_type == "odometer":
            if asset.asset_class != "vehicle":
                raise AssetValidation()
            reading = data.value.get("reading")
            unit = data.value.get("unit")
            if (
                isinstance(reading, bool)
                or not isinstance(reading, (int, float))
                or reading < 0
                or unit not in {"MILES", "KILOMETERS"}
            ):
                raise AssetValidation()
            latest = await session.scalar(
                select(AssetEvidence)
                .where(
                    AssetEvidence.company_id == asset.company_id,
                    AssetEvidence.asset_id == asset.id,
                    AssetEvidence.evidence_type == "odometer",
                    AssetEvidence.state != "conflicting_evidence",
                )
                .order_by(AssetEvidence.occurred_at.desc(), AssetEvidence.id.desc())
                .limit(1)
            )
            if latest is not None:
                prior = latest.value.get("reading")
                prior_unit = latest.value.get("unit")
                if (
                    prior_unit == unit
                    and isinstance(prior, (int, float))
                    and reading < prior
                ):
                    # A regression must be admitted explicitly as conflicting/correction
                    # evidence; it cannot silently replace the accepted projection.
                    raise AssetConflict()

    async def relate(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        asset_id: UUID,
        data: RelationshipCreate,
    ) -> AssetRelationship:
        row = await self._asset(session, context, asset_id, lock=True)
        raw = data.model_dump(mode="json", exclude={"idempotency_key"})
        request = digest(raw)
        replay = await session.scalar(
            select(AssetRelationship).where(
                AssetRelationship.company_id == context.company.id,
                AssetRelationship.idempotency_key == data.idempotency_key,
            )
        )
        if replay:
            if replay.asset_id != row.id or replay.request_digest != request:
                raise AssetConflict()
            return replay
        await self._validate_related_entity(session, context, row, data)
        if data.relationship_type in {
            "customer",
            "service_location",
            "employee_custody",
            "inventory_location",
        }:
            overlap = await session.scalar(
                select(AssetRelationship)
                .where(
                    AssetRelationship.company_id == context.company.id,
                    AssetRelationship.asset_id == row.id,
                    AssetRelationship.relationship_type == data.relationship_type,
                    or_(
                        AssetRelationship.valid_to.is_(None),
                        AssetRelationship.valid_to > data.valid_from,
                    ),
                    AssetRelationship.valid_from < data.valid_to
                    if data.valid_to is not None
                    else AssetRelationship.valid_from.is_not(None),
                )
                .with_for_update()
            )
            if overlap:
                raise AssetConflict()
        evidence_digest = digest({"asset": row.identity_digest, **raw})
        item = AssetRelationship(
            company_id=context.company.id,
            branch_id=row.branch_id,
            asset_id=row.id,
            relationship_type=data.relationship_type,
            related_entity_id=data.related_entity_id,
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            evidence_digest=evidence_digest,
            request_digest=request,
            idempotency_key=data.idempotency_key,
            actor_user_id=context.user.id,
        )
        session.add(item)
        await session.flush()
        self._event(
            session,
            row,
            context.user.id,
            EventType.ASSET_RELATIONSHIP_RECORDED,
            data.relationship_type,
            evidence_digest,
        )
        await session.commit()
        await session.refresh(item)
        return item

    async def _validate_related_entity(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        asset: Asset,
        data: RelationshipCreate,
    ) -> None:
        """Resolve typed references inside the caller's tenant and branch scope.

        Relationship IDs are deliberately polymorphic, so this validation is the
        decisive fail-closed boundary that a conventional foreign key cannot express.
        """
        related_id = data.related_entity_id
        company_id = context.company.id
        if data.relationship_type == "customer":
            found = await session.scalar(
                select(Customer.id).where(
                    Customer.id == related_id, Customer.company_id == company_id
                )
            )
        elif data.relationship_type == "service_location":
            found = await session.scalar(
                select(ServiceLocation.id)
                .join(Customer, Customer.id == ServiceLocation.customer_id)
                .where(
                    ServiceLocation.id == related_id,
                    Customer.company_id == company_id,
                )
            )
        elif data.relationship_type == "job":
            found = await session.scalar(
                select(Job.id).where(
                    Job.id == related_id,
                    Job.company_id == company_id,
                    Job.branch_id == asset.branch_id,
                )
            )
        elif data.relationship_type == "employee_custody":
            found = await session.scalar(
                select(Employee.id).where(
                    Employee.id == related_id,
                    Employee.company_id == company_id,
                    or_(
                        Employee.home_branch_id.is_(None),
                        Employee.home_branch_id == asset.branch_id,
                    ),
                )
            )
        elif data.relationship_type == "inventory_location":
            found = await session.scalar(
                select(StockLocation.id).where(
                    StockLocation.id == related_id,
                    StockLocation.company_id == company_id,
                    StockLocation.branch_id == asset.branch_id,
                )
            )
        elif data.relationship_type == "branch_custody":
            found = await session.scalar(
                select(Branch.id).where(
                    Branch.id == related_id,
                    Branch.company_id == company_id,
                    Branch.id.in_(context.authorized_branch_ids),
                )
            )
        elif data.relationship_type == "vehicle_custody":
            found = await session.scalar(
                select(Asset.id).where(
                    Asset.id == related_id,
                    Asset.company_id == company_id,
                    Asset.branch_id == asset.branch_id,
                    Asset.asset_class == "vehicle",
                )
            )
        else:
            # Dispatch and other future composition must introduce a typed resolver;
            # accepting an opaque UUID would fabricate cross-domain authority.
            raise AssetValidation()
        if found is None:
            raise AssetNotFound()

    async def transition(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        asset_id: UUID,
        data: LifecycleChange,
    ) -> Asset:
        row = await self._asset(session, context, asset_id, lock=True)
        raw = data.model_dump(mode="json", exclude={"idempotency_key"})
        request = digest(raw)
        replay = await session.scalar(
            select(AssetLifecycleEvidence).where(
                AssetLifecycleEvidence.company_id == context.company.id,
                AssetLifecycleEvidence.idempotency_key == data.idempotency_key,
            )
        )
        if replay:
            if replay.asset_id != row.id or replay.request_digest != request:
                raise AssetConflict()
            return row
        if row.version != data.expected_version:
            raise AssetConflict()
        allowed = {
            "active": {"inactive", "retired", "replaced", "disposed"},
            "inactive": {"active", "retired", "disposed"},
        }
        if data.lifecycle not in allowed.get(row.lifecycle, set()):
            raise AssetValidation()
        prior = row.lifecycle
        row.lifecycle = data.lifecycle
        row.version += 1
        row.updated_at = datetime.now(timezone.utc)
        evidence_digest = digest({"asset": row.identity_digest, "prior": prior, **raw})
        session.add(
            AssetLifecycleEvidence(
                company_id=context.company.id,
                branch_id=row.branch_id,
                asset_id=row.id,
                prior_state=prior,
                resulting_state=data.lifecycle,
                reason=data.reason,
                request_digest=request,
                evidence_digest=evidence_digest,
                idempotency_key=data.idempotency_key,
                actor_user_id=context.user.id,
            )
        )
        self._event(
            session,
            row,
            context.user.id,
            EventType.ASSET_LIFECYCLE_CHANGED,
            data.lifecycle,
            evidence_digest,
        )
        await session.commit()
        await session.refresh(row)
        return row

    async def record_action(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        asset_id: UUID,
        data: AssetActionCreate,
    ) -> AssetActionEvidence:
        row = await self._asset(session, context, asset_id, lock=True)
        raw = data.model_dump(mode="json", exclude={"idempotency_key"})
        request = digest(raw)
        replay = await session.scalar(
            select(AssetActionEvidence).where(
                AssetActionEvidence.company_id == context.company.id,
                AssetActionEvidence.idempotency_key == data.idempotency_key,
            )
        )
        if replay:
            if replay.asset_id != row.id or replay.request_digest != request:
                raise AssetConflict()
            return replay
        if row.version != data.expected_version:
            raise AssetConflict()
        await self._validate_action(session, context, row, data)
        evidence_digest = digest({"asset": row.identity_digest, **raw})
        item = AssetActionEvidence(
            company_id=context.company.id,
            branch_id=row.branch_id,
            asset_id=row.id,
            action_type=data.action_type,
            state=data.state,
            related_entity_id=data.related_entity_id,
            payload=data.payload,
            occurred_at=data.occurred_at,
            asset_version=row.version + 1,
            request_digest=request,
            evidence_digest=evidence_digest,
            idempotency_key=data.idempotency_key,
            actor_user_id=context.user.id,
        )
        row.version += 1
        row.updated_at = datetime.now(timezone.utc)
        session.add(item)
        self._event(
            session,
            row,
            context.user.id,
            EventType.ASSET_EVIDENCE_RECORDED,
            data.action_type,
            evidence_digest,
        )
        await session.commit()
        await session.refresh(item)
        return item

    async def action_history(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        asset_id: UUID,
        limit: int,
    ) -> list[AssetActionEvidence]:
        row = await self._asset(session, context, asset_id)
        return list(
            (
                await session.scalars(
                    select(AssetActionEvidence)
                    .where(
                        AssetActionEvidence.company_id == context.company.id,
                        AssetActionEvidence.asset_id == row.id,
                    )
                    .order_by(
                        AssetActionEvidence.occurred_at.desc(),
                        AssetActionEvidence.id.desc(),
                    )
                    .limit(limit)
                )
            ).all()
        )

    async def _validate_action(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        asset: Asset,
        data: AssetActionCreate,
    ) -> None:
        equipment_actions = {
            "equipment_install",
            "equipment_remove",
            "equipment_replace",
            "warranty_evidence",
            "warranty_review",
            "service_link",
        }
        vehicle_actions = {
            "vehicle_assignment",
            "inspection",
            "maintenance",
            "out_of_service",
        }
        custody_actions = {"custody_transfer", "custody_return"}
        if (
            data.action_type in equipment_actions
            and asset.asset_class != "customer_equipment"
        ):
            raise AssetValidation()
        if data.action_type in vehicle_actions and asset.asset_class != "vehicle":
            raise AssetValidation()
        if data.action_type in custody_actions and asset.asset_class not in {
            "tool",
            "equipment",
        }:
            raise AssetValidation()
        if data.action_type == "equipment_install":
            customer_id = self._payload_uuid(data.payload, "customer_id")
            location_id = self._payload_uuid(data.payload, "service_location_id")
            found = await session.scalar(
                select(ServiceLocation.id)
                .join(Customer, Customer.id == ServiceLocation.customer_id)
                .where(
                    Customer.id == customer_id,
                    Customer.company_id == context.company.id,
                    ServiceLocation.id == location_id,
                )
            )
            if found is None:
                raise AssetNotFound()
        if data.action_type == "service_link":
            job_id = data.related_entity_id or self._payload_uuid(
                data.payload, "job_id"
            )
            found = await session.scalar(
                select(Job.id).where(
                    Job.id == job_id,
                    Job.company_id == context.company.id,
                    Job.branch_id == asset.branch_id,
                )
            )
            if found is None:
                raise AssetNotFound()
        if data.action_type == "vehicle_assignment":
            employee_id = data.related_entity_id or self._payload_uuid(
                data.payload, "employee_id"
            )
            found = await session.scalar(
                select(Employee.id).where(
                    Employee.id == employee_id,
                    Employee.company_id == context.company.id,
                    or_(
                        Employee.home_branch_id.is_(None),
                        Employee.home_branch_id == asset.branch_id,
                    ),
                )
            )
            if found is None:
                raise AssetNotFound()
        if data.action_type in {
            "warranty_review",
            "out_of_service",
        } and not data.payload.get("reason"):
            raise AssetValidation()

    @staticmethod
    def _payload_uuid(payload: dict[str, object], key: str) -> UUID:
        try:
            return UUID(str(payload[key]))
        except (KeyError, TypeError, ValueError) as error:
            raise AssetValidation() from error

    @staticmethod
    def readiness(row: Asset, evidence: list[AssetEvidence]) -> tuple[str, list[str]]:
        if row.lifecycle in {"inactive", "retired", "replaced", "disposed"}:
            return "OUT_OF_SERVICE", [f"lifecycle:{row.lifecycle}"]
        states = {(x.evidence_type, x.state) for x in evidence}
        if any(state == "fail" for _, state in states):
            return "ATTENTION_REQUIRED", ["an accepted check requires attention"]
        if any(state == "attention_required" for _, state in states):
            return "ATTENTION_REQUIRED", ["attention evidence is open"]
        if ("inspection", "due") in states:
            return "INSPECTION_DUE", ["inspection policy/evidence reports due"]
        if ("maintenance", "due") in states:
            return "MAINTENANCE_DUE", ["maintenance policy/evidence reports due"]
        if ("inspection", "insufficient_evidence") in states:
            return "INSPECTION_REQUIRED", ["inspection evidence is insufficient"]
        if ("maintenance", "deferred") in states:
            return "MAINTENANCE_DUE", ["maintenance is deferred"]
        if row.asset_class == "vehicle":
            if not any(x.evidence_type == "powertrain" for x in evidence):
                return "INSUFFICIENT_EVIDENCE", ["vehicle powertrain is not recorded"]
            if not any(
                x.evidence_type == "readiness" and x.state == "verified"
                for x in evidence
            ):
                return "POLICY_REQUIRED", [
                    "vehicle readiness policy/evidence is unconfigured"
                ]
        return "READY", []

    @staticmethod
    def _event(
        session: AsyncSession,
        row: Asset,
        actor: UUID,
        event_type: EventType,
        action: str,
        evidence_digest: str,
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="operational_asset",
                entity_id=row.id,
                company_id=row.company_id,
                branch_id=row.branch_id,
                user_id=actor,
                payload={
                    "schema_version": "1.0",
                    "asset_class": row.asset_class,
                    "action": action,
                    "evidence_digest": evidence_digest,
                },
            ),
        )


asset_service = AssetService()

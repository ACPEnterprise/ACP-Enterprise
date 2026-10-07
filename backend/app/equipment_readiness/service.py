import hashlib
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dispatch.models import DispatchAssignment
from app.equipment_readiness.domain import equipment_checklist_prompt_required
from app.equipment_readiness.models import (
    EquipmentAttention,
    EquipmentCatalogItem,
    EquipmentCustodyEvent,
    EquipmentDailyConfirmation,
    EquipmentPlacement,
    EquipmentSetComponent,
    ServiceEquipmentRequirement,
)
from app.equipment_readiness.schemas import (
    CatalogCreate,
    ComponentCreate,
    CustodyTransferRequest,
    DailyConfirmationRequest,
    EquipmentChecklistSetting,
    PlacementCreate,
    RequirementCreate,
)
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.jobs.models import Job
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext


class EquipmentReadinessError(Exception):
    pass


class EquipmentNotFound(EquipmentReadinessError):
    pass


class EquipmentConflict(EquipmentReadinessError):
    pass


class EquipmentValidation(EquipmentReadinessError):
    pass


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


STATE_MAP = {
    "present_ready": "ready",
    "transferred": "unknown",
    "left_at_shop": "unknown",
    "in_repair": "out_of_service",
    "missing_or_unknown": "missing",
    "incomplete_set": "incomplete",
    "broken_or_out_of_service": "out_of_service",
    "other": "unknown",
}


class EquipmentReadinessService:
    @staticmethod
    def _scope(context: AuthorizationContext, branch_id: UUID) -> None:
        if not context.can_access_branch(branch_id):
            raise EquipmentNotFound()

    async def catalog(self, session: AsyncSession, context: AuthorizationContext, branch_id: UUID | None = None):
        branches = (branch_id,) if branch_id else context.authorized_branch_ids
        if branch_id:
            self._scope(context, branch_id)
        return list((await session.scalars(select(EquipmentCatalogItem).where(
            EquipmentCatalogItem.company_id == context.company.id,
            EquipmentCatalogItem.branch_id.in_(branches),
        ).order_by(EquipmentCatalogItem.display_name))).all())

    async def create_catalog(self, session: AsyncSession, context: AuthorizationContext, data: CatalogCreate):
        self._scope(context, data.branch_id)
        existing = await session.scalar(select(EquipmentCatalogItem).where(
            EquipmentCatalogItem.company_id == context.company.id,
            EquipmentCatalogItem.code == data.code.strip().upper(),
        ))
        if existing:
            same = (
                existing.display_name == data.display_name.strip()
                and existing.capability_code == data.capability_code.strip().upper()
                and existing.item_kind == data.item_kind
                and existing.serialization_required == data.serialization_required
            )
            if not same:
                raise EquipmentConflict()
            return existing
        if data.serialization_required and data.item_kind != "controlled_asset":
            raise EquipmentValidation()
        row = EquipmentCatalogItem(
            company_id=context.company.id, branch_id=data.branch_id,
            code=data.code.strip().upper(), display_name=data.display_name.strip(),
            capability_code=data.capability_code.strip().upper(), item_kind=data.item_kind,
            serialization_required=data.serialization_required, provenance=data.provenance,
            created_by_user_id=context.user.id,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    async def add_component(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        catalog_item_id: UUID,
        data: ComponentCreate,
    ):
        catalog = await session.scalar(
            select(EquipmentCatalogItem).where(
                EquipmentCatalogItem.id == catalog_item_id,
                EquipmentCatalogItem.company_id == context.company.id,
                EquipmentCatalogItem.branch_id.in_(context.authorized_branch_ids),
            )
        )
        if catalog is None:
            raise EquipmentNotFound()
        if catalog.item_kind != "equipment_set":
            raise EquipmentValidation()
        code = data.component_code.strip().upper()
        existing = await session.scalar(
            select(EquipmentSetComponent).where(
                EquipmentSetComponent.company_id == context.company.id,
                EquipmentSetComponent.catalog_item_id == catalog.id,
                EquipmentSetComponent.component_code == code,
            )
        )
        if existing:
            if (
                existing.display_name != data.display_name.strip()
                or existing.required_quantity != data.required_quantity
            ):
                raise EquipmentConflict()
            return existing
        row = EquipmentSetComponent(
            company_id=context.company.id,
            catalog_item_id=catalog.id,
            component_code=code,
            display_name=data.display_name.strip(),
            required_quantity=data.required_quantity,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    async def create_placement(self, session: AsyncSession, context: AuthorizationContext, data: PlacementCreate):
        self._scope(context, data.branch_id)
        request = digest(data.model_dump(mode="json", exclude={"idempotency_key"}))
        replay = await session.scalar(
            select(EquipmentPlacement).where(
                EquipmentPlacement.company_id == context.company.id,
                EquipmentPlacement.idempotency_key == data.idempotency_key,
            )
        )
        if replay:
            if replay.request_digest != request:
                raise EquipmentConflict()
            return replay
        item = await session.scalar(select(EquipmentCatalogItem).where(
            EquipmentCatalogItem.id == data.catalog_item_id,
            EquipmentCatalogItem.company_id == context.company.id,
            EquipmentCatalogItem.branch_id == data.branch_id,
            EquipmentCatalogItem.status == "active",
        ))
        if item is None:
            raise EquipmentNotFound()
        if item.serialization_required and data.asset_id is None:
            raise EquipmentValidation()
        if data.current_custodian_employee_id:
            await self._employee(session, context, data.current_custodian_employee_id, data.branch_id)
        row = EquipmentPlacement(
            company_id=context.company.id, branch_id=data.branch_id,
            catalog_item_id=data.catalog_item_id, asset_id=data.asset_id,
            home_kind=data.home_kind, home_entity_id=data.home_entity_id,
            current_location_kind=data.current_location_kind,
            current_location_entity_id=data.current_location_entity_id,
            current_custodian_employee_id=data.current_custodian_employee_id,
            custody_effective_at=data.effective_at, readiness_state="unknown",
            request_digest=request, idempotency_key=data.idempotency_key,
        )
        session.add(row)
        await session.flush()
        session.add(self._custody_event(row, context.user.id, "assigned", None, data.current_custodian_employee_id, data.current_location_kind, data.current_location_entity_id, "Initial governed placement", "unknown", "unknown", data.effective_at, f"{data.idempotency_key}:event", request))
        await session.commit()
        await session.refresh(row)
        return row

    async def daily_prompt(self, session: AsyncSession, context: AuthorizationContext, employee_id: UUID, work_date: date):
        employee = await self._employee(session, context, employee_id)
        if employee.equipment_checklist_requirement != "required_at_clock_in":
            return {
                "employee_id": employee.id, "work_date": work_date,
                "required": False,
                "reason": "Equipment checklist is not required for this Employee.",
                "already_confirmed": False, "items": (),
            }
        placements = list((await session.scalars(select(EquipmentPlacement).where(
            EquipmentPlacement.company_id == context.company.id,
            EquipmentPlacement.branch_id.in_(context.authorized_branch_ids),
            EquipmentPlacement.current_custodian_employee_id == employee.id,
        ).order_by(EquipmentPlacement.id))).all())
        item_ids = {row.catalog_item_id for row in placements}
        items = {row.id: row for row in (await session.scalars(select(EquipmentCatalogItem).where(
            EquipmentCatalogItem.company_id == context.company.id,
            EquipmentCatalogItem.status == "active",
            EquipmentCatalogItem.id.in_(item_ids),
        ))).all()} if item_ids else {}
        confirmations = list((await session.scalars(select(EquipmentDailyConfirmation).where(
            EquipmentDailyConfirmation.company_id == context.company.id,
            EquipmentDailyConfirmation.employee_id == employee.id,
            EquipmentDailyConfirmation.work_date == work_date,
        ))).all())
        latest = {row.catalog_item_id: row for row in sorted(confirmations, key=lambda x: (x.confirmed_at, x.id))}
        prompt = []
        for placement in placements:
            item = items.get(placement.catalog_item_id)
            if item is None:
                continue
            prior = latest.get(item.id)
            prompt.append({
                "catalog_item_id": item.id, "code": item.code,
                "display_name": item.display_name, "item_kind": item.item_kind,
                "placement_id": placement.id,
                "default_state": prior.state if prior else "present_ready",
                "readiness_state": placement.readiness_state,
                "last_confirmed_at": placement.last_confirmed_at,
            })
        return {
            "employee_id": employee.id, "work_date": work_date,
            "required": equipment_checklist_prompt_required(
                employee.equipment_checklist_requirement,
                has_custody_items=bool(prompt),
                already_confirmed=bool(latest),
            ),
            "reason": "Confirm the equipment expected in your custody." if prompt else "No dispatch-critical equipment is assigned to you.",
            "already_confirmed": bool(latest), "items": tuple(prompt),
        }

    async def get_checklist_setting(self, session, context, employee_id: UUID):
        employee = await self._employee(session, context, employee_id)
        return employee

    async def set_checklist_setting(
        self, session, context, employee_id: UUID, data: EquipmentChecklistSetting
    ):
        employee = await self._employee(session, context, employee_id)
        employee.equipment_checklist_requirement = data.equipment_checklist_requirement
        employee.updated_by_user_id = context.user.id
        await session.commit()
        await session.refresh(employee)
        return employee

    async def confirm(self, session: AsyncSession, context: AuthorizationContext, data: DailyConfirmationRequest):
        employee = await self._employee(session, context, data.employee_id)
        if employee.home_branch_id is None:
            raise EquipmentValidation()
        base_digest = digest(data.model_dump(mode="json", exclude={"idempotency_key"}))
        prior = list((await session.scalars(select(EquipmentDailyConfirmation).where(
            EquipmentDailyConfirmation.company_id == context.company.id,
            EquipmentDailyConfirmation.idempotency_key.like(f"{data.idempotency_key}:%"),
        ).order_by(EquipmentDailyConfirmation.catalog_item_id))).all())
        if prior:
            if len(prior) != len(data.items) or any(row.request_digest != base_digest for row in prior):
                raise EquipmentConflict()
            return prior
        results = []
        for index, item_data in enumerate(data.items):
            catalog = await session.scalar(select(EquipmentCatalogItem).where(
                EquipmentCatalogItem.id == item_data.catalog_item_id,
                EquipmentCatalogItem.company_id == context.company.id,
                EquipmentCatalogItem.status == "active",
            ))
            if catalog is None:
                raise EquipmentNotFound()
            placement = None
            if item_data.placement_id:
                placement = await self._placement(session, context, item_data.placement_id, lock=True)
                if placement.current_custodian_employee_id != employee.id:
                    raise EquipmentConflict()
            if item_data.state == "incomplete_set" and catalog.item_kind != "equipment_set":
                raise EquipmentValidation()
            if item_data.state == "incomplete_set":
                configured = set((await session.scalars(select(EquipmentSetComponent.component_code).where(
                    EquipmentSetComponent.company_id == context.company.id,
                    EquipmentSetComponent.catalog_item_id == catalog.id,
                ))).all())
                supplied = {value.strip().upper() for value in item_data.missing_components}
                if not configured or not supplied.issubset(configured):
                    raise EquipmentValidation()
            latest = await session.scalar(select(EquipmentDailyConfirmation).where(
                EquipmentDailyConfirmation.company_id == context.company.id,
                EquipmentDailyConfirmation.employee_id == employee.id,
                EquipmentDailyConfirmation.catalog_item_id == catalog.id,
                EquipmentDailyConfirmation.work_date == data.work_date,
            ).order_by(EquipmentDailyConfirmation.confirmed_at.desc(), EquipmentDailyConfirmation.id.desc()).limit(1))
            row = EquipmentDailyConfirmation(
                company_id=context.company.id, branch_id=employee.home_branch_id,
                employee_id=employee.id, catalog_item_id=catalog.id,
                placement_id=placement.id if placement else None,
                work_date=data.work_date, state=item_data.state,
                missing_components=item_data.missing_components, note=item_data.note,
                supersedes_confirmation_id=latest.id if latest else None,
                confirmed_at=data.confirmed_at, actor_user_id=context.user.id,
                request_digest=base_digest,
                evidence_digest=digest({"request": base_digest, "item": item_data.model_dump(mode="json"), "ordinal": index}),
                idempotency_key=f"{data.idempotency_key}:{index}",
            )
            session.add(row)
            results.append(row)
            readiness = STATE_MAP[item_data.state]
            if placement:
                if item_data.state == "transferred":
                    if item_data.receiving_employee_id:
                        await self._employee(
                            session, context, item_data.receiving_employee_id, placement.branch_id
                        )
                    transfer_event = self._custody_event(
                        placement, context.user.id, "transferred",
                        placement.current_custodian_employee_id,
                        item_data.receiving_employee_id,
                        item_data.receiving_location_kind or "employee",
                        item_data.receiving_location_entity_id,
                        item_data.note or "Transferred during daily equipment confirmation",
                        placement.readiness_state, "unknown", data.confirmed_at,
                        f"{data.idempotency_key}:transfer:{index}", base_digest,
                    )
                    session.add(transfer_event)
                    placement.current_custodian_employee_id = item_data.receiving_employee_id
                    placement.current_location_kind = item_data.receiving_location_kind or "employee"
                    placement.current_location_entity_id = item_data.receiving_location_entity_id
                    placement.custody_effective_at = data.confirmed_at
                placement.last_confirmed_at = data.confirmed_at
                placement.readiness_state = readiness
                placement.missing_components = item_data.missing_components
                placement.updated_at = data.confirmed_at
                placement.version += 1
            if readiness != "ready":
                await self._upsert_attention(session, context, employee, catalog, placement, item_data, data.confirmed_at)
            else:
                await self._resolve_matching_attention(session, context, employee.id, catalog.id, data.confirmed_at)
        BusinessEventService.stage(session, BusinessEventCreate(
            event_type=EventType.EQUIPMENT_READINESS_CONFIRMED,
            entity_type="employee", entity_id=employee.id,
            company_id=context.company.id, branch_id=employee.home_branch_id,
            user_id=context.user.id,
            payload={"work_date": str(data.work_date), "item_count": len(results), "has_exception": any(x.state != "present_ready" for x in results)},
        ))
        await session.commit()
        for row in results:
            await session.refresh(row)
        return results

    async def transfer(self, session: AsyncSession, context: AuthorizationContext, placement_id: UUID, data: CustodyTransferRequest):
        row = await self._placement(session, context, placement_id, lock=True)
        replay = await session.scalar(select(EquipmentCustodyEvent).where(
            EquipmentCustodyEvent.company_id == context.company.id,
            EquipmentCustodyEvent.idempotency_key == data.idempotency_key,
        ))
        request = digest(data.model_dump(mode="json", exclude={"idempotency_key"}))
        if replay:
            if replay.placement_id != row.id or replay.request_digest != request:
                raise EquipmentConflict()
            return replay
        if row.version != data.expected_version:
            raise EquipmentConflict()
        if data.to_employee_id:
            await self._employee(session, context, data.to_employee_id, row.branch_id)
        event = self._custody_event(row, context.user.id, data.event_type, row.current_custodian_employee_id, data.to_employee_id, data.to_location_kind, data.to_location_entity_id, data.reason, row.readiness_state, data.resulting_state, data.occurred_at, data.idempotency_key, request)
        session.add(event)
        row.current_custodian_employee_id = data.to_employee_id
        row.current_location_kind = data.to_location_kind
        row.current_location_entity_id = data.to_location_entity_id
        row.custody_effective_at = data.occurred_at
        row.readiness_state = data.resulting_state
        row.service_state = "in_repair" if data.event_type == "repair" else "out_of_service" if data.event_type in {"broken", "lost"} else "available"
        row.updated_at = data.occurred_at
        row.version += 1
        BusinessEventService.stage(session, BusinessEventCreate(
            event_type=EventType.EQUIPMENT_CUSTODY_CHANGED,
            entity_type="equipment_placement", entity_id=row.id,
            company_id=context.company.id, branch_id=row.branch_id, user_id=context.user.id,
            payload={"event_type": data.event_type, "resulting_state": data.resulting_state},
        ))
        await session.commit()
        await session.refresh(event)
        return event

    async def add_requirement(self, session: AsyncSession, context: AuthorizationContext, data: RequirementCreate):
        self._scope(context, data.branch_id)
        if data.source_type == "job":
            found = await session.scalar(select(Job.id).where(Job.id == data.source_entity_id, Job.company_id == context.company.id, Job.branch_id == data.branch_id))
            if found is None:
                raise EquipmentNotFound()
        existing = await session.scalar(select(ServiceEquipmentRequirement).where(
            ServiceEquipmentRequirement.company_id == context.company.id,
            ServiceEquipmentRequirement.source_type == data.source_type,
            ServiceEquipmentRequirement.source_entity_id == data.source_entity_id,
            ServiceEquipmentRequirement.capability_code == data.capability_code.strip().upper(),
        ))
        if existing:
            return existing
        row = ServiceEquipmentRequirement(
            company_id=context.company.id, branch_id=data.branch_id,
            source_type=data.source_type, source_entity_id=data.source_entity_id,
            capability_code=data.capability_code.strip().upper(),
            requirement_reason=data.requirement_reason.strip(), provenance=data.provenance,
            created_by_user_id=context.user.id,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    async def dispatch_readiness(self, session: AsyncSession, context: AuthorizationContext, branch_id: UUID):
        self._scope(context, branch_id)
        employees = list((await session.scalars(select(Employee).where(
            Employee.company_id == context.company.id, Employee.home_branch_id == branch_id,
            Employee.status == "active", Employee.archived_at.is_(None),
        ).order_by(Employee.display_name))).all())
        placements = list((await session.scalars(select(EquipmentPlacement).where(
            EquipmentPlacement.company_id == context.company.id,
            EquipmentPlacement.branch_id == branch_id,
        ))).all())
        by_employee: dict[UUID, list[EquipmentPlacement]] = {}
        for row in placements:
            if row.current_custodian_employee_id:
                by_employee.setdefault(row.current_custodian_employee_id, []).append(row)
        result = []
        for employee in employees:
            assigned = by_employee.get(employee.id, [])
            states = {x.readiness_state for x in assigned}
            if not assigned or "unknown" in states or "missing" in states:
                state = "EQUIPMENT_UNKNOWN"
            elif "out_of_service" in states:
                state = "EQUIPMENT_OUT_OF_SERVICE"
            elif "incomplete" in states:
                state = "EQUIPMENT_SET_INCOMPLETE"
            else:
                state = "AVAILABLE_AND_EQUIPPED"
            result.append({
                "employee_id": employee.id, "employee_name": employee.display_name,
                "branch_id": branch_id, "state": state,
                "warning_codes": tuple(sorted(states - {"ready"})),
                "missing_capabilities": (), "scheduling_eligible": None,
            })
        return result

    async def job_fit(self, session: AsyncSession, context: AuthorizationContext, job_id: UUID, employee_id: UUID):
        job = await session.scalar(select(Job).where(Job.id == job_id, Job.company_id == context.company.id, Job.branch_id.in_(context.authorized_branch_ids)))
        if job is None:
            raise EquipmentNotFound()
        await self._employee(session, context, employee_id, job.branch_id)
        requirements = list((await session.scalars(select(ServiceEquipmentRequirement).where(
            ServiceEquipmentRequirement.company_id == context.company.id,
            ServiceEquipmentRequirement.source_type == "job",
            ServiceEquipmentRequirement.source_entity_id == job.id,
            ServiceEquipmentRequirement.status == "active",
        ))).all())
        placements = list((await session.scalars(select(EquipmentPlacement).where(
            EquipmentPlacement.company_id == context.company.id,
            EquipmentPlacement.current_custodian_employee_id == employee_id,
        ))).all())
        item_ids = {x.catalog_item_id for x in placements if x.readiness_state == "ready"}
        capabilities = set((await session.scalars(select(EquipmentCatalogItem.capability_code).where(
            EquipmentCatalogItem.company_id == context.company.id,
            EquipmentCatalogItem.id.in_(item_ids),
        ))).all()) if item_ids else set()
        required = {x.capability_code for x in requirements}
        missing = required - capabilities
        return {
            "job_id": job.id, "employee_id": employee_id,
            "state": "AVAILABLE_AND_EQUIPPED" if not missing else "AVAILABLE_EQUIPMENT_WARNING",
            "soft_warning": bool(missing), "required_capabilities": tuple(sorted(required)),
            "missing_capabilities": tuple(sorted(missing)), "continuation_allowed": True,
            "override_reason_required": bool(missing),
        }

    async def attention(self, session: AsyncSession, context: AuthorizationContext, branch_id: UUID | None = None):
        role_codes = {x.code for x in context.effective_roles}
        if not role_codes.intersection({"OWNER", "COMPANY_ADMINISTRATOR", "FIELD_MANAGER", "FIELD_SERVICE_MANAGER"}):
            return []
        stmt = select(EquipmentAttention).where(
            EquipmentAttention.company_id == context.company.id,
            EquipmentAttention.state == "open",
            EquipmentAttention.branch_id.in_(context.authorized_branch_ids),
        )
        if branch_id:
            self._scope(context, branch_id)
            stmt = stmt.where(EquipmentAttention.branch_id == branch_id)
        return list((await session.scalars(stmt.order_by(EquipmentAttention.priority, EquipmentAttention.first_observed_at))).all())

    async def refresh_upcoming_attention(
        self, session: AsyncSession, context: AuthorizationContext,
        branch_id: UUID, as_of: datetime, horizon_hours: int,
    ):
        self._scope(context, branch_id)
        assignments = list((await session.scalars(select(DispatchAssignment).where(
            DispatchAssignment.company_id == context.company.id,
            DispatchAssignment.branch_id == branch_id,
            DispatchAssignment.primary_employee_id.is_not(None),
            DispatchAssignment.job_id.is_not(None),
            DispatchAssignment.status.in_(("proposed", "assigned", "acknowledged", "reconciliation_required")),
            DispatchAssignment.window_start_at >= as_of,
            DispatchAssignment.window_start_at <= as_of + timedelta(hours=horizon_hours),
        ))).all())
        impacted: list[EquipmentAttention] = []
        for assignment in assignments:
            assert assignment.job_id is not None
            assert assignment.primary_employee_id is not None
            fit = await self.job_fit(
                session, context, assignment.job_id, assignment.primary_employee_id
            )
            for capability in fit["missing_capabilities"]:
                identity = f"equipment-job:{assignment.id}:{capability}"
                evidence = digest({
                    "assignment": assignment.id, "job": assignment.job_id,
                    "employee": assignment.primary_employee_id,
                    "capability": capability, "window": assignment.window_start_at,
                })
                row = await session.scalar(select(EquipmentAttention).where(
                    EquipmentAttention.company_id == context.company.id,
                    EquipmentAttention.identity_key == identity,
                ).with_for_update())
                if row is None:
                    row = EquipmentAttention(
                        company_id=context.company.id, branch_id=branch_id,
                        identity_key=identity,
                        attention_code="EQUIPMENT_REQUIRED_FOR_UPCOMING_JOB",
                        priority="critical_before_job", employee_id=assignment.primary_employee_id,
                        job_id=assignment.job_id, appointment_id=assignment.appointment_id,
                        title="Equipment needed before an upcoming job",
                        explanation=f"Required capability {capability} is not confirmed for the assigned technician.",
                        responsibility_code="FIELD_OPERATIONS", first_observed_at=as_of,
                        last_observed_at=as_of, evidence_digest=evidence,
                    )
                    session.add(row)
                else:
                    row.last_observed_at = as_of
                    row.evidence_digest = evidence
                    row.state = "open"
                    row.priority = "critical_before_job"
                    row.version += 1
                impacted.append(row)
        await session.commit()
        for row in impacted:
            await session.refresh(row)
        return impacted

    async def resolve_attention(self, session: AsyncSession, context: AuthorizationContext, attention_id: UUID, note: str, expected_version: int):
        row = await session.scalar(select(EquipmentAttention).where(
            EquipmentAttention.id == attention_id,
            EquipmentAttention.company_id == context.company.id,
            EquipmentAttention.branch_id.in_(context.authorized_branch_ids),
        ).with_for_update())
        if row is None:
            raise EquipmentNotFound()
        if row.version != expected_version or row.state != "open":
            raise EquipmentConflict()
        row.state = "resolved"; row.resolved_at = datetime.now(timezone.utc)
        row.resolved_by_user_id = context.user.id; row.resolution_note = note.strip(); row.version += 1
        await session.commit(); await session.refresh(row); return row

    async def intelligence(self, session: AsyncSession, context: AuthorizationContext):
        rows = await self.attention(session, context)
        counts = Counter(row.priority for row in rows)
        return {
            "as_of": datetime.now(timezone.utc), "attention_count": len(rows),
            "impacted_job_count": len({row.job_id for row in rows if row.job_id}),
            "readiness_counts": dict(counts),
            "limitations": ("Read-only evidence; Beacon and Luminary have no custody or resolution mutation authority.", "No equipment requirement is inferred from Job free text."),
        }

    async def _employee(self, session, context, employee_id, branch_id=None):
        stmt = select(Employee).where(Employee.id == employee_id, Employee.company_id == context.company.id, Employee.status.not_in(("terminated", "inactive")), Employee.archived_at.is_(None))
        if branch_id:
            self._scope(context, branch_id)
            stmt = stmt.where(Employee.home_branch_id == branch_id)
        else:
            stmt = stmt.where(or_(Employee.home_branch_id.is_(None), Employee.home_branch_id.in_(context.authorized_branch_ids)))
        row = await session.scalar(stmt)
        if row is None:
            raise EquipmentNotFound()
        return row

    async def _placement(self, session, context, placement_id, lock=False):
        stmt = select(EquipmentPlacement).where(EquipmentPlacement.id == placement_id, EquipmentPlacement.company_id == context.company.id, EquipmentPlacement.branch_id.in_(context.authorized_branch_ids))
        if lock: stmt = stmt.with_for_update()
        row = await session.scalar(stmt)
        if row is None: raise EquipmentNotFound()
        return row

    def _custody_event(self, row, actor, event_type, from_employee, to_employee, to_kind, to_id, reason, source, resulting, occurred, key, request=None):
        request = request or digest({"placement": row.id, "event": event_type, "to": to_employee, "at": occurred})
        return EquipmentCustodyEvent(
            company_id=row.company_id, branch_id=row.branch_id, placement_id=row.id,
            event_type=event_type, from_employee_id=from_employee, to_employee_id=to_employee,
            from_location_kind=row.current_location_kind, to_location_kind=to_kind,
            to_location_entity_id=to_id, reason=reason, source_state=source,
            resulting_state=resulting, occurred_at=occurred, actor_user_id=actor,
            request_digest=request, evidence_digest=digest({"request": request, "placement": row.id}), idempotency_key=key,
        )

    async def _upsert_attention(self, session, context, employee, catalog, placement, item, observed_at):
        row = await session.scalar(select(EquipmentAttention).where(
            EquipmentAttention.company_id == context.company.id,
            EquipmentAttention.employee_id == employee.id,
            EquipmentAttention.catalog_item_id == catalog.id,
            EquipmentAttention.job_id.is_(None),
            EquipmentAttention.state == "open",
        ).with_for_update())
        code = item.state.upper()
        title = f"{catalog.display_name} needs attention"
        explanation = item.note or f"{employee.display_name} reported {item.state.replace('_', ' ')}."
        value_digest = digest({"employee": employee.id, "catalog": catalog.id, "state": item.state, "missing": item.missing_components})
        if row:
            row.last_observed_at = observed_at; row.evidence_digest = value_digest
            row.attention_code = code; row.title = title; row.explanation = explanation; row.version += 1
        else:
            identity = f"equipment:{employee.id}:{catalog.id}:{value_digest[:16]}"
            session.add(EquipmentAttention(
                company_id=context.company.id, branch_id=employee.home_branch_id,
                identity_key=identity, attention_code=code, priority="needs_attention",
                employee_id=employee.id, catalog_item_id=catalog.id,
                placement_id=placement.id if placement else None, title=title,
                explanation=explanation, responsibility_code="FIELD_OPERATIONS",
                first_observed_at=observed_at, last_observed_at=observed_at,
                evidence_digest=value_digest,
            ))

    async def _resolve_matching_attention(self, session, context, employee_id, catalog_id, observed_at):
        rows = list((await session.scalars(select(EquipmentAttention).where(
            EquipmentAttention.company_id == context.company.id,
            EquipmentAttention.employee_id == employee_id,
            EquipmentAttention.catalog_item_id == catalog_id,
            EquipmentAttention.state == "open",
        ).with_for_update())).all())
        for row in rows:
            row.state = "resolved"; row.resolved_at = observed_at
            row.resolved_by_user_id = context.user.id; row.resolution_note = "Equipment confirmed ready"; row.version += 1


equipment_readiness_service = EquipmentReadinessService()

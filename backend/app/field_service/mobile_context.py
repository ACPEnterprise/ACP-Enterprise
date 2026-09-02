from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer, ServiceLocation
from app.dispatch.models import DispatchAssignment, DispatchCrewMember
from app.estimates.models import (
    Estimate,
    EstimateJobConversion,
    EstimateLineItem,
    EstimateRevision,
)
from app.field_service.schemas import (
    FieldEquipmentItem,
    FieldEquipmentProjection,
    FieldEstimateLine,
    FieldEstimatePresentation,
    FieldEvidenceSummary,
    FieldFleetItem,
    FieldHistoryItem,
    FieldHistoryProjection,
    FieldReadinessProjection,
)
from app.field_service.service import field_service
from app.jobs.models import Job
from app.operational_assets.models import (
    Asset,
    AssetActionEvidence,
    AssetEvidence,
    AssetOperationalPolicy,
    AssetRelationship,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.models import Appointment
from app.workforce.models import (
    WorkforceBranchEligibility,
    WorkforceCapabilityProfile,
    WorkforceWorkingAvailability,
)


def _safe_value(evidence: AssetEvidence) -> str | None:
    """Return only explicitly field-safe descriptive evidence, never identifiers."""
    for key in ("display_name", "name", "manufacturer", "model"):
        value = evidence.value.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:200]
    return None


class MobileFieldContext:
    HISTORY_LIMIT = 10

    async def equipment(
        self, session: AsyncSession, *, context: AuthorizationContext, job_id: UUID
    ) -> FieldEquipmentProjection:
        assignment = await field_service._assigned_job(session, context, job_id)
        relationship_asset_ids = select(AssetRelationship.asset_id).where(
            AssetRelationship.company_id == context.company.id,
            AssetRelationship.branch_id == assignment.branch_id,
            AssetRelationship.relationship_type == "job",
            AssetRelationship.related_entity_id == job_id,
            AssetRelationship.valid_to.is_(None),
        )
        assets = tuple(
            (
                await session.scalars(
                    select(Asset)
                    .where(
                        Asset.company_id == context.company.id,
                        Asset.branch_id == assignment.branch_id,
                        Asset.asset_class == "customer_equipment",
                        Asset.id.in_(relationship_asset_ids),
                    )
                    .order_by(Asset.display_name, Asset.id)
                    .limit(25)
                )
            ).all()
        )
        items: list[FieldEquipmentItem] = []
        evidence_by_asset: dict[UUID, list[AssetEvidence]] = defaultdict(list)
        if assets:
            all_evidence = tuple(
                (
                    await session.scalars(
                        select(AssetEvidence)
                        .where(
                            AssetEvidence.company_id == context.company.id,
                            AssetEvidence.branch_id == assignment.branch_id,
                            AssetEvidence.asset_id.in_(
                                tuple(asset.id for asset in assets)
                            ),
                            AssetEvidence.evidence_type.in_(
                                (
                                    "manufacturer",
                                    "model",
                                    "installation",
                                    "replacement",
                                    "job_service",
                                    "warranty",
                                    "inspection",
                                    "maintenance",
                                    "readiness",
                                    "document",
                                )
                            ),
                        )
                        .order_by(
                            AssetEvidence.asset_id,
                            AssetEvidence.occurred_at.desc(),
                            AssetEvidence.id,
                        )
                        .limit(750)
                    )
                ).all()
            )
            for item in all_evidence:
                if len(evidence_by_asset[item.asset_id]) < 30:
                    evidence_by_asset[item.asset_id].append(item)
        for asset in assets:
            evidence = tuple(evidence_by_asset[asset.id])
            latest = {item.evidence_type: item for item in reversed(evidence)}
            history = tuple(
                FieldEvidenceSummary(
                    kind=item.evidence_type,
                    state=item.state,
                    occurred_at=item.occurred_at,
                    protected_document_available=item.protected_document_id is not None,
                )
                for item in evidence
                if item.evidence_type in ("job_service", "replacement", "maintenance")
            )[: self.HISTORY_LIMIT]
            safe_evidence = tuple(
                FieldEvidenceSummary(
                    kind=item.evidence_type,
                    state=item.state,
                    occurred_at=item.occurred_at,
                    protected_document_available=item.protected_document_id is not None,
                )
                for item in evidence
                if item.evidence_type
                in ("installation", "warranty", "inspection", "readiness", "document")
            )[: self.HISTORY_LIMIT]
            items.append(
                FieldEquipmentItem(
                    asset_id=asset.id,
                    display_name=asset.display_name,
                    lifecycle=asset.lifecycle,
                    manufacturer=_safe_value(latest["manufacturer"])
                    if "manufacturer" in latest
                    else None,
                    model=_safe_value(latest["model"]) if "model" in latest else None,
                    installation_state=latest["installation"].state
                    if "installation" in latest
                    else None,
                    warranty_state=latest["warranty"].state
                    if "warranty" in latest
                    else None,
                    service_history=history,
                    evidence=safe_evidence,
                )
            )
        return FieldEquipmentProjection(
            job_id=job_id, items=tuple(items), history_limit=self.HISTORY_LIMIT
        )

    async def estimate(
        self, session: AsyncSession, *, context: AuthorizationContext, job_id: UUID
    ) -> FieldEstimatePresentation:
        assignment = await field_service._assigned_job(session, context, job_id)
        conversion = await session.scalar(
            select(EstimateJobConversion).where(
                EstimateJobConversion.company_id == context.company.id,
                EstimateJobConversion.branch_id == assignment.branch_id,
                EstimateJobConversion.job_id == job_id,
            )
        )
        if conversion is None:
            return FieldEstimatePresentation(job_id=job_id, available=False)
        estimate = await session.scalar(
            select(Estimate).where(
                Estimate.company_id == context.company.id,
                Estimate.branch_id == assignment.branch_id,
                Estimate.id == conversion.estimate_id,
                Estimate.current_revision_id == conversion.estimate_revision_id,
            )
        )
        revision = await session.scalar(
            select(EstimateRevision).where(
                EstimateRevision.company_id == context.company.id,
                EstimateRevision.id == conversion.estimate_revision_id,
                EstimateRevision.status == "issued",
            )
        )
        if estimate is None or revision is None:
            return FieldEstimatePresentation(job_id=job_id, available=False)
        lines = tuple(
            FieldEstimateLine(
                position=line.position,
                title=line.title,
                description=line.description,
                quantity=line.quantity,
                line_total=line.line_total,
                currency=line.currency,
            )
            for line in (
                await session.scalars(
                    select(EstimateLineItem)
                    .where(
                        EstimateLineItem.company_id == context.company.id,
                        EstimateLineItem.revision_id == revision.id,
                    )
                    .order_by(EstimateLineItem.position)
                    .limit(50)
                )
            ).all()
        )
        return FieldEstimatePresentation(
            job_id=job_id,
            available=True,
            estimate_number=estimate.estimate_number,
            estimate_status=estimate.status,
            acceptance_status=estimate.acceptance_status,
            revision_number=revision.revision_number,
            revision_status=revision.status,
            proposal_title=revision.proposal_title,
            customer_message=revision.customer_message,
            total_amount=revision.total_amount,
            currency=revision.currency,
            expires_at=revision.expires_at,
            lines=lines,
        )

    async def history(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        days: int,
        limit: int,
    ) -> FieldHistoryProjection:
        employee = await field_service._employee(session, context)
        crew_ids = select(DispatchCrewMember.assignment_id).where(
            DispatchCrewMember.company_id == context.company.id,
            DispatchCrewMember.employee_id == employee.id,
        )
        since = datetime.now(timezone.utc) - timedelta(days=days)
        rows = (
            await session.execute(
                select(Job, DispatchAssignment, Appointment, Customer, ServiceLocation)
                .join(DispatchAssignment, DispatchAssignment.job_id == Job.id)
                .join(Appointment, Appointment.id == DispatchAssignment.appointment_id)
                .join(Customer, Customer.id == Appointment.customer_id)
                .join(
                    ServiceLocation,
                    ServiceLocation.id == Appointment.service_location_id,
                )
                .where(
                    Job.company_id == context.company.id,
                    Job.branch_id.in_(context.authorized_branch_ids),
                    Job.status == "completed",
                    Job.completed_at >= since,
                    or_(
                        DispatchAssignment.primary_employee_id == employee.id,
                        DispatchAssignment.id.in_(crew_ids),
                    ),
                )
                .order_by(Job.completed_at.desc(), Job.id)
                .limit(limit)
            )
        ).all()
        return FieldHistoryProjection(
            days=days,
            limit=limit,
            items=tuple(
                FieldHistoryItem(
                    job_id=job.id,
                    job_number=job.job_number,
                    completed_at=job.completed_at,
                    customer_display_name=customer.display_name,
                    service_location_label=field_service._location_label(location),
                )
                for job, _assignment, _appointment, customer, location in rows
                if job.completed_at is not None
            ),
        )

    async def readiness(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> FieldReadinessProjection:
        employee = await field_service._employee(session, context)
        profile = await session.scalar(
            select(WorkforceCapabilityProfile).where(
                WorkforceCapabilityProfile.company_id == context.company.id,
                WorkforceCapabilityProfile.employee_id == employee.id,
                WorkforceCapabilityProfile.status == "active",
            )
        )
        now = datetime.now(timezone.utc)
        eligible = False
        availability = None
        if profile is not None:
            eligible = (
                await session.scalar(
                    select(WorkforceBranchEligibility.id)
                    .where(
                        WorkforceBranchEligibility.company_id == context.company.id,
                        WorkforceBranchEligibility.profile_id == profile.id,
                        WorkforceBranchEligibility.branch_id.in_(
                            context.authorized_branch_ids
                        ),
                        WorkforceBranchEligibility.status == "active",
                    )
                    .limit(1)
                )
            ) is not None
            availability = await session.scalar(
                select(WorkforceWorkingAvailability.status)
                .where(
                    WorkforceWorkingAvailability.company_id == context.company.id,
                    WorkforceWorkingAvailability.profile_id == profile.id,
                    WorkforceWorkingAvailability.branch_id.in_(
                        context.authorized_branch_ids
                    ),
                    WorkforceWorkingAvailability.start_at <= now,
                    WorkforceWorkingAvailability.end_at >= now,
                )
                .order_by(WorkforceWorkingAvailability.start_at.desc())
                .limit(1)
            )
        relation_ids = select(AssetRelationship.asset_id).where(
            AssetRelationship.company_id == context.company.id,
            AssetRelationship.branch_id.in_(context.authorized_branch_ids),
            AssetRelationship.relationship_type == "employee_custody",
            AssetRelationship.related_entity_id == employee.id,
            AssetRelationship.valid_to.is_(None),
        )
        assets = tuple(
            (
                await session.scalars(
                    select(Asset)
                    .where(
                        Asset.company_id == context.company.id,
                        Asset.branch_id.in_(context.authorized_branch_ids),
                        Asset.id.in_(relation_ids),
                        Asset.asset_class.in_(("vehicle", "tool", "equipment")),
                    )
                    .order_by(Asset.asset_class, Asset.display_name)
                    .limit(25)
                )
            ).all()
        )
        fleet: list[FieldFleetItem] = []
        evidence_by_asset: dict[UUID, list[AssetEvidence]] = defaultdict(list)
        actions_by_asset: dict[UUID, list[AssetActionEvidence]] = defaultdict(list)
        if assets:
            asset_ids = tuple(asset.id for asset in assets)
            all_evidence = tuple(
                (
                    await session.scalars(
                        select(AssetEvidence)
                        .where(
                            AssetEvidence.company_id == context.company.id,
                            AssetEvidence.asset_id.in_(asset_ids),
                            AssetEvidence.evidence_type.in_(
                                ("readiness", "inspection", "maintenance", "custody")
                            ),
                        )
                        .order_by(
                            AssetEvidence.asset_id,
                            AssetEvidence.occurred_at.desc(),
                        )
                        .limit(250)
                    )
                ).all()
            )
            all_actions = tuple(
                (
                    await session.scalars(
                        select(AssetActionEvidence)
                        .where(
                            AssetActionEvidence.company_id == context.company.id,
                            AssetActionEvidence.asset_id.in_(asset_ids),
                            AssetActionEvidence.action_type.in_(
                                ("inspection", "maintenance", "out_of_service")
                            ),
                        )
                        .order_by(
                            AssetActionEvidence.asset_id,
                            AssetActionEvidence.occurred_at.desc(),
                        )
                        .limit(250)
                    )
                ).all()
            )
            for item in all_evidence:
                if len(evidence_by_asset[item.asset_id]) < 10:
                    evidence_by_asset[item.asset_id].append(item)
            for item in all_actions:
                if len(actions_by_asset[item.asset_id]) < 10:
                    actions_by_asset[item.asset_id].append(item)
        for asset in assets:
            evidence = tuple(evidence_by_asset[asset.id])
            latest = {item.evidence_type: item.state for item in reversed(evidence)}
            actions = tuple(actions_by_asset[asset.id])
            latest_action = {
                item.action_type: item.state for item in reversed(actions)
            }
            fleet.append(
                FieldFleetItem(
                    asset_id=asset.id,
                    display_name=asset.display_name,
                    lifecycle=asset.lifecycle,
                    readiness_state=latest.get("readiness"),
                    inspection_state=latest_action.get(
                        "inspection", latest.get("inspection")
                    ),
                    maintenance_state=latest_action.get(
                        "maintenance", latest.get("maintenance")
                    ),
                    out_of_service=asset.lifecycle != "active"
                    or latest.get("readiness") == "fail"
                    or latest_action.get("out_of_service")
                    not in (None, "cleared", "completed", "canceled"),
                    custody_state=latest.get("custody"),
                )
            )
        inspection_policy = await session.scalar(
            select(AssetOperationalPolicy.id)
            .where(
                AssetOperationalPolicy.company_id == context.company.id,
                AssetOperationalPolicy.branch_id.in_(context.authorized_branch_ids),
                AssetOperationalPolicy.policy_type == "inspection",
                AssetOperationalPolicy.status == "active",
            )
            .limit(1)
        )
        return FieldReadinessProjection(
            fleet=tuple(fleet),
            workforce_profile_available=profile is not None,
            branch_eligible=eligible,
            availability_state=availability,
            inspection_interaction=(
                "source_required" if inspection_policy else "policy_required"
            ),
        )


mobile_field_context = MobileFieldContext()

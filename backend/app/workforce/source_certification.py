from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.operational_migration.models import HcpEmployeeSourceCrosswalk
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.branch.models import Branch
from app.platform.employees.models import Employee
from app.platform.onboarding.models import IdentityOnboardingRequest
from app.platform.permissions.authorization import AuthorizationContext
from app.workforce.models import (
    WorkforceSourceCertification,
    WorkforceSourceCertificationRevision,
)
from app.workforce.schemas import (
    SourceCertificationDecisionRequest,
    SourceCertificationItem,
    SourceCertificationLedger,
    SourceCertificationRevisionItem,
)


class SourceCertificationConflict(ValueError):
    pass


class SourceCertificationService:
    async def ledger(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> SourceCertificationLedger:
        source_records = tuple(
            (
                await session.scalars(
                    select(HcpEmployeeSourceCrosswalk)
                    .where(HcpEmployeeSourceCrosswalk.company_id == context.company.id)
                    .order_by(
                        HcpEmployeeSourceCrosswalk.native_employee_id,
                        HcpEmployeeSourceCrosswalk.evidence_version.desc(),
                    )
                )
            ).all()
        )
        latest: dict[str, HcpEmployeeSourceCrosswalk] = {}
        for source in source_records:
            latest.setdefault(source.native_employee_id, source)
        certifications = {
            item.source_employee_id: item
            for item in (
                await session.scalars(
                    select(WorkforceSourceCertification).where(
                        WorkforceSourceCertification.company_id == context.company.id,
                        WorkforceSourceCertification.source_system == "HCP",
                    )
                )
            ).all()
        }
        employee_ids = {
            value
            for source in latest.values()
            for value in (source.employee_id,)
            if value is not None
        } | {
            value
            for item in certifications.values()
            for value in (item.employee_id,)
            if value is not None
        }
        employees = (
            {
                item.id: item
                for item in (
                    await session.scalars(
                        select(Employee).where(
                            Employee.company_id == context.company.id,
                            Employee.id.in_(employee_ids),
                        )
                    )
                ).all()
            }
            if employee_ids
            else {}
        )
        branch_ids = {source.branch_id for source in latest.values()}
        branches = {
            item.id: item.name
            for item in (
                await session.scalars(
                    select(Branch).where(
                        Branch.company_id == context.company.id,
                        Branch.id.in_(branch_ids),
                    )
                )
            ).all()
        }
        revision_rows = tuple(
            (
                await session.scalars(
                    select(WorkforceSourceCertificationRevision)
                    .join(
                        WorkforceSourceCertification,
                        WorkforceSourceCertification.id
                        == WorkforceSourceCertificationRevision.certification_id,
                    )
                    .where(
                        WorkforceSourceCertification.company_id == context.company.id
                    )
                    .order_by(
                        WorkforceSourceCertificationRevision.certification_id,
                        WorkforceSourceCertificationRevision.revision,
                    )
                )
            ).all()
        )
        history: dict[UUID, list[SourceCertificationRevisionItem]] = {}
        for revision in revision_rows:
            history.setdefault(revision.certification_id, []).append(
                SourceCertificationRevisionItem(
                    revision=revision.revision,
                    decision=revision.decision,
                    employee_id=revision.employee_id,
                    onboarding_request_id=revision.onboarding_request_id,
                    actor_user_id=revision.actor_user_id,
                    reason=revision.reason,
                    occurred_at=revision.occurred_at,
                )
            )
        items = tuple(
            self._item(
                source,
                certifications.get(source.native_employee_id),
                employees,
                branches[source.branch_id],
                history,
            )
            for source in latest.values()
        )
        return SourceCertificationLedger(
            items=items,
            total=len(items),
            undecided=sum(item.decision is None for item in items),
        )

    async def decide(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        source_employee_id: str,
        command: SourceCertificationDecisionRequest,
    ) -> SourceCertificationLedger:
        now = datetime.now(timezone.utc)
        async with session.begin():
            source = await session.scalar(
                select(HcpEmployeeSourceCrosswalk)
                .where(
                    HcpEmployeeSourceCrosswalk.company_id == context.company.id,
                    HcpEmployeeSourceCrosswalk.native_employee_id == source_employee_id,
                )
                .order_by(HcpEmployeeSourceCrosswalk.evidence_version.desc())
                .limit(1)
            )
            if source is None:
                raise SourceCertificationConflict(
                    "Source Employee evidence is unavailable."
                )
            current = await session.scalar(
                select(WorkforceSourceCertification)
                .where(
                    WorkforceSourceCertification.company_id == context.company.id,
                    WorkforceSourceCertification.source_system == "HCP",
                    WorkforceSourceCertification.source_employee_id
                    == source_employee_id,
                )
                .with_for_update()
            )
            revision = current.current_revision if current else 0
            employee_id, onboarding_id = await self._targets(
                session, context, source, command
            )
            if (
                current is not None
                and revision == command.expected_revision + 1
                and current.current_decision == command.decision
                and current.employee_id == employee_id
                and current.onboarding_request_id == onboarding_id
                and current.reason == command.reason
            ):
                return await self.ledger(session, context=context)
            if revision != command.expected_revision:
                raise SourceCertificationConflict("Certification revision is stale.")
            competing = (
                await session.scalar(
                    select(WorkforceSourceCertification).where(
                        WorkforceSourceCertification.company_id == context.company.id,
                        WorkforceSourceCertification.employee_id == employee_id,
                        WorkforceSourceCertification.current_decision.in_(
                            ("CONFIRM", "SELECT_EXISTING")
                        ),
                        WorkforceSourceCertification.id
                        != (current.id if current else UUID(int=0)),
                    )
                )
                if employee_id is not None
                else None
            )
            if competing is not None:
                raise SourceCertificationConflict(
                    "Employee is already certified to another source identity."
                )
            next_revision = revision + 1
            if current is None:
                current = WorkforceSourceCertification(
                    company_id=context.company.id,
                    source_system="HCP",
                    source_employee_id=source.native_employee_id,
                    evidence_reference=f"hcp_employee_source_crosswalk:{source.id}",
                    evidence_digest=source.evidence_digest,
                    branch_id=source.branch_id,
                    current_decision=command.decision,
                    current_revision=next_revision,
                    employee_id=employee_id,
                    onboarding_request_id=onboarding_id,
                    decided_by_user_id=context.user.id,
                    reason=command.reason,
                    decided_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(current)
                await session.flush()
                prior = None
            else:
                prior = await session.scalar(
                    select(WorkforceSourceCertificationRevision).where(
                        WorkforceSourceCertificationRevision.certification_id
                        == current.id,
                        WorkforceSourceCertificationRevision.revision == revision,
                    )
                )
                current.current_decision = command.decision
                current.current_revision = next_revision
                current.employee_id = employee_id
                current.onboarding_request_id = onboarding_id
                current.decided_by_user_id = context.user.id
                current.reason = command.reason
                current.decided_at = now
                current.updated_at = now
            record = WorkforceSourceCertificationRevision(
                certification_id=current.id,
                revision=next_revision,
                prior_revision_id=prior.id if prior else None,
                decision=command.decision,
                evidence_reference=current.evidence_reference,
                evidence_digest=current.evidence_digest,
                branch_id=current.branch_id,
                employee_id=employee_id,
                onboarding_request_id=onboarding_id,
                actor_user_id=context.user.id,
                reason=command.reason,
                occurred_at=now,
            )
            session.add(record)
            audit_service.stage(
                session,
                AuditEntry(
                    action="workforce.source_employee_certified",
                    resource_type="workforce_source_certification",
                    resource_id=current.id,
                    actor_user_id=context.user.id,
                    company_id=context.company.id,
                    branch_id=source.branch_id,
                    details={
                        "source_system": "HCP",
                        "source_employee_id": source.native_employee_id,
                        "decision": command.decision,
                        "revision": next_revision,
                        "employee_id": str(employee_id) if employee_id else None,
                    },
                ),
            )
        return await self.ledger(session, context=context)

    @staticmethod
    async def _targets(session, context, source, command):
        employee_id = None
        onboarding_id = None
        if command.decision == "CONFIRM":
            employee_id = source.employee_id
            if employee_id is None:
                raise SourceCertificationConflict(
                    "Source evidence has no ACP Employee candidate."
                )
        elif command.decision == "SELECT_EXISTING":
            employee_id = command.employee_id
            if employee_id is None:
                raise SourceCertificationConflict(
                    "An exact existing Employee is required."
                )
        elif command.decision == "CREATE_ONBOARD":
            onboarding_id = command.onboarding_request_id
        elif (
            command.employee_id is not None or command.onboarding_request_id is not None
        ):
            raise SourceCertificationConflict(
                "Hold and legacy decisions cannot bind a target."
            )
        if employee_id is not None:
            employee = await session.scalar(
                select(Employee).where(
                    Employee.company_id == context.company.id,
                    Employee.id == employee_id,
                )
            )
            if employee is None:
                raise SourceCertificationConflict(
                    "Employee target is outside Company authority."
                )
        if onboarding_id is not None:
            onboarding = await session.scalar(
                select(IdentityOnboardingRequest).where(
                    IdentityOnboardingRequest.company_id == context.company.id,
                    IdentityOnboardingRequest.id == onboarding_id,
                )
            )
            if onboarding is None:
                raise SourceCertificationConflict(
                    "Onboarding target is outside Company authority."
                )
        return employee_id, onboarding_id

    @staticmethod
    def _item(source, certification, employees, branch_name, history):
        supported = employees.get(source.employee_id)
        selected = employees.get(certification.employee_id) if certification else None
        return SourceCertificationItem(
            source_system="HCP",
            source_employee_id=source.native_employee_id,
            source_disposition=source.disposition,
            source_branch_id=source.branch_id,
            source_branch_name=branch_name,
            evidence_reference=f"hcp_employee_source_crosswalk:{source.id}",
            evidence_digest=source.evidence_digest,
            mechanically_supported_employee_id=source.employee_id,
            mechanically_supported_employee_name=supported.display_name
            if supported
            else None,
            decision=certification.current_decision if certification else None,
            revision=certification.current_revision if certification else 0,
            employee_id=certification.employee_id if certification else None,
            employee_name=selected.display_name if selected else None,
            onboarding_request_id=certification.onboarding_request_id
            if certification
            else None,
            reason=certification.reason if certification else None,
            decided_at=certification.decided_at if certification else None,
            history=tuple(history.get(certification.id, ())) if certification else (),
        )


source_certification_service = SourceCertificationService()

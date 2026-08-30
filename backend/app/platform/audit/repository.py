from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.audit.contracts import AuditQuery, AuditRecordView
from app.platform.audit.models import AuditRecord


class AuditReadRepository:
    async def list_company_records(
        self, session: AsyncSession, *, query: AuditQuery
    ) -> tuple[AuditRecordView, ...]:
        statement: Select[tuple[AuditRecord]] = select(AuditRecord).where(
            AuditRecord.company_id == query.company_id
        )
        if query.branch_id is not None:
            statement = statement.where(AuditRecord.branch_id == query.branch_id)
        elif not query.has_all_branch_access:
            statement = statement.where(
                AuditRecord.branch_id.in_(query.authorized_branch_ids)
            )
        if query.actor_user_id is not None:
            statement = statement.where(
                AuditRecord.actor_user_id == query.actor_user_id
            )
        if query.resource_type is not None:
            statement = statement.where(
                AuditRecord.resource_type == query.resource_type
            )
        if query.action is not None:
            statement = statement.where(AuditRecord.action == query.action)
        if query.outcome is not None:
            statement = statement.where(AuditRecord.outcome == query.outcome)
        if query.correlation_id is not None:
            statement = statement.where(
                AuditRecord.correlation_id == query.correlation_id
            )
        if query.occurred_before is not None:
            if query.before_id is None:
                statement = statement.where(
                    AuditRecord.occurred_at < query.occurred_before
                )
            else:
                statement = statement.where(
                    or_(
                        AuditRecord.occurred_at < query.occurred_before,
                        and_(
                            AuditRecord.occurred_at == query.occurred_before,
                            AuditRecord.id < query.before_id,
                        ),
                    )
                )
        records = await session.scalars(
            statement.order_by(
                AuditRecord.occurred_at.desc(), AuditRecord.id.desc()
            ).limit(query.limit)
        )
        return tuple(
            AuditRecordView(
                id=record.id,
                action=record.action,
                outcome=record.outcome,
                actor_user_id=record.actor_user_id,
                company_id=record.company_id,  # type: ignore[arg-type]
                branch_id=record.branch_id,
                resource_type=record.resource_type,
                resource_id=record.resource_id,
                reason_code=record.reason_code,
                correlation_id=record.correlation_id,
                details=record.details,
                occurred_at=record.occurred_at,
            )
            for record in records
        )


audit_read_repository = AuditReadRepository()

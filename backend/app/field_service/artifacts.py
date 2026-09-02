"""Assignment-scoped append-only Job artifact custody."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.permissions.authorization import AuthorizationContext

from .errors import FieldServiceConflict, FieldServiceNotFound, FieldServiceValidation
from .models import FieldArtifactEvidence, FieldArtifactIntent
from .schemas import (
    FieldArtifactFinalizeInput,
    FieldArtifactIntentInput,
    FieldArtifactIntentOut,
    FieldArtifactOut,
)
from .service import FieldService


def _digest(facts: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class FieldArtifactService:
    def __init__(self, field: FieldService) -> None:
        self.field = field

    async def create_intent(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        payload: FieldArtifactIntentInput,
    ) -> FieldArtifactIntentOut:
        assignment = await self.field._assigned_job(session, context, job_id)
        if assignment.version != payload.expected_assignment_version:
            raise FieldServiceConflict("Field assignment changed. Refresh and retry.")
        facts: dict[str, object] = {
            "company_id": str(context.company.id),
            "branch_id": str(assignment.branch_id),
            "job_id": str(job_id),
            "assignment_id": str(assignment.id),
            "artifact_class": payload.artifact_class,
            "media_type": payload.media_type,
            "expected_size": payload.expected_size,
            "expected_digest": payload.expected_digest,
            "idempotency_key": payload.idempotency_key,
        }
        request_digest = _digest(facts)
        existing = await session.scalar(
            select(FieldArtifactIntent).where(
                FieldArtifactIntent.company_id == context.company.id,
                FieldArtifactIntent.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_digest != request_digest:
                raise FieldServiceConflict(
                    "Artifact intent identity is bound to different evidence."
                )
            return self._intent(existing)
        now = datetime.now(timezone.utc)
        intent_id = uuid4()
        record = FieldArtifactIntent(
            id=intent_id,
            company_id=context.company.id,
            branch_id=assignment.branch_id,
            job_id=job_id,
            assignment_id=assignment.id,
            artifact_class=payload.artifact_class,
            media_type=payload.media_type,
            expected_size=payload.expected_size,
            expected_digest=payload.expected_digest,
            opaque_upload_reference=f"field-upload:{intent_id}",
            expires_at=now + timedelta(minutes=20),
            request_digest=request_digest,
            idempotency_key=payload.idempotency_key,
            created_by_user_id=context.user.id,
            created_at=now,
        )
        session.add(record)
        await session.commit()
        return self._intent(record)

    async def finalize(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        intent_id: UUID,
        payload: FieldArtifactFinalizeInput,
    ) -> FieldArtifactOut:
        assignment = await self.field._assigned_job(session, context, job_id)
        intent = await session.scalar(
            select(FieldArtifactIntent)
            .where(
                FieldArtifactIntent.company_id == context.company.id,
                FieldArtifactIntent.branch_id == assignment.branch_id,
                FieldArtifactIntent.job_id == job_id,
                FieldArtifactIntent.assignment_id == assignment.id,
                FieldArtifactIntent.id == intent_id,
            )
            .with_for_update()
        )
        if intent is None:
            raise FieldServiceNotFound("Field artifact intent was not found.")
        existing = await session.scalar(
            select(FieldArtifactEvidence).where(
                FieldArtifactEvidence.company_id == context.company.id,
                FieldArtifactEvidence.intent_id == intent.id,
            )
        )
        if existing is not None:
            if (
                existing.content_digest != payload.content_digest
                or existing.size != payload.size
                or existing.media_type != payload.media_type
                or existing.opaque_storage_reference
                != payload.opaque_storage_reference
            ):
                raise FieldServiceConflict(
                    "Artifact finalization is bound to different evidence."
                )
            return self._artifact(existing)
        now = datetime.now(timezone.utc)
        if intent.expires_at <= now:
            raise FieldServiceConflict("Field artifact upload intent expired.")
        if (
            payload.content_digest != intent.expected_digest
            or payload.size != intent.expected_size
            or payload.media_type != intent.media_type
        ):
            raise FieldServiceValidation(
                "Final artifact does not match the admitted upload intent."
            )
        facts: dict[str, object] = {
            "intent_id": str(intent.id),
            "company_id": str(context.company.id),
            "branch_id": str(assignment.branch_id),
            "job_id": str(job_id),
            "assignment_id": str(assignment.id),
            "artifact_class": intent.artifact_class,
            "media_type": payload.media_type,
            "size": payload.size,
            "content_digest": payload.content_digest,
            "opaque_storage_reference": payload.opaque_storage_reference,
        }
        evidence = FieldArtifactEvidence(
            company_id=context.company.id,
            branch_id=assignment.branch_id,
            job_id=job_id,
            assignment_id=assignment.id,
            intent_id=intent.id,
            artifact_class=intent.artifact_class,
            media_type=payload.media_type,
            size=payload.size,
            content_digest=payload.content_digest,
            opaque_storage_reference=payload.opaque_storage_reference,
            evidence_digest=_digest(facts),
            recorded_by_user_id=context.user.id,
            created_at=now,
        )
        session.add(evidence)
        await session.flush()
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=EventType.FIELD_ARTIFACT_RECORDED,
                entity_type="field_artifact",
                entity_id=evidence.id,
                company_id=context.company.id,
                branch_id=assignment.branch_id,
                user_id=context.user.id,
                correlation_id=uuid4(),
                payload={
                    "job_id": str(job_id),
                    "assignment_id": str(assignment.id),
                    "artifact_class": intent.artifact_class,
                    "content_digest": payload.content_digest,
                },
            ),
        )
        await session.commit()
        return self._artifact(evidence)

    @staticmethod
    def _intent(record: FieldArtifactIntent) -> FieldArtifactIntentOut:
        return FieldArtifactIntentOut(
            intent_id=record.id,
            job_id=record.job_id,
            upload_reference=record.opaque_upload_reference,
            expires_at=record.expires_at,
            provider_state="provider_required",
        )

    @staticmethod
    def _artifact(record: FieldArtifactEvidence) -> FieldArtifactOut:
        return FieldArtifactOut(
            artifact_id=record.id,
            job_id=record.job_id,
            artifact_class=record.artifact_class,
            media_type=record.media_type,
            size=record.size,
            content_digest=record.content_digest,
            created_at=record.created_at,
        )


field_artifact_service = FieldArtifactService(FieldService())

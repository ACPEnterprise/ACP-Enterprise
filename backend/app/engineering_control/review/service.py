import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizationService,
    PermissionDeniedError,
    authorization_service,
)
from app.platform.permissions.codes import EngineeringCommandPermission

from .contracts import EngineeringReviewDecision, EngineeringReviewState
from .errors import (
    EngineeringReviewConflictError,
    EngineeringReviewDigestMismatchError,
    EngineeringReviewIneligibleError,
    EngineeringReviewNotFoundError,
)
from .records import (
    DecideEngineeringReview,
    EngineeringReviewPackage,
    EngineeringReviewRecord,
)
from .repository import EngineeringReviewRepository, EngineeringReviewSource

REASON_CODE = re.compile(r"^[a-z][a-z0-9_]{2,79}$")
MAX_REVIEW_JSON_BYTES = 32_000
MAX_OUTPUT_REFERENCES = 20


def calculate_review_digest(source: EngineeringReviewSource) -> str:
    payload = {
        "command_id": str(source.command.id),
        "execution_id": str(source.execution.id),
        "composition_id": str(source.composition.id),
        "attempt_id": str(source.attempt.id),
        "result_id": str(source.result.id),
        "provider_identifier": source.composition.provider_identifier,
        "instruction_digest": source.composition.instruction_digest,
        "request_digest": source.composition.request_digest,
        "composition_digest": source.composition.composition_digest,
        "result_status": source.result.status,
        "result_disposition": source.result.disposition,
        "evidence_summary": source.result.evidence_summary,
        "validation_summary": source.result.validation_summary,
        "output_references": source.result.output_references,
        "repository_mutated": source.result.repository_mutated,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EngineeringReviewService:
    def __init__(
        self,
        *,
        repository: type[EngineeringReviewRepository] = EngineeringReviewRepository,
        authorization: AuthorizationService = authorization_service,
        audit: AuditService = audit_service,
        events: type[BusinessEventService] = BusinessEventService,
    ) -> None:
        self.repository = repository
        self.authorization = authorization
        self.audit = audit
        self.events = events

    async def prepare(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command_id: UUID,
        now: datetime | None = None,
    ) -> EngineeringReviewPackage:
        self._require(context, EngineeringCommandPermission.APPROVE)
        occurred_at = now or utc_now()
        try:
            async with session.begin():
                source = await self.repository.load_completed_source_for_update(
                    session,
                    company_id=context.company.id,
                    command_id=command_id,
                )
                if source is None:
                    raise EngineeringReviewNotFoundError(
                        "Completed Engineering result was not found."
                    )
                self._validate_source(source)
                digest = self._review_digest(source)
                review = await self.repository.get_by_result(
                    session,
                    company_id=context.company.id,
                    result_id=source.result.id,
                )
                if review is None:
                    review = await self.repository.create(
                        session,
                        source=source,
                        review_digest=digest,
                        now=occurred_at,
                    )
                    self._stage(
                        session,
                        context=context,
                        review=review,
                        event_type=EventType.ENGINEERING_REVIEW_PREPARED,
                        action="engineering.review_prepared",
                        details={"state": review.state.value},
                        now=occurred_at,
                    )
                elif review.review_digest != digest:
                    raise EngineeringReviewDigestMismatchError(
                        "Durable review evidence does not match the result."
                    )
                decision = await self.repository.get_decision(
                    session,
                    company_id=context.company.id,
                    review_id=review.id,
                )
                return self._package(review, source, decision)
        except IntegrityError:
            await session.rollback()
            async with session.begin():
                source = await self.repository.load_completed_source_for_update(
                    session,
                    company_id=context.company.id,
                    command_id=command_id,
                )
                if source is None:
                    raise EngineeringReviewNotFoundError(
                        "Completed Engineering result was not found."
                    )
                review = await self.repository.get_by_result(
                    session,
                    company_id=context.company.id,
                    result_id=source.result.id,
                )
                if review is None or review.review_digest != self._review_digest(
                    source
                ):
                    raise EngineeringReviewConflictError(
                        "Review preparation conflicted."
                    )
                decision = await self.repository.get_decision(
                    session,
                    company_id=context.company.id,
                    review_id=review.id,
                )
                return self._package(review, source, decision)

    async def get(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        review_id: UUID,
    ) -> EngineeringReviewPackage:
        self._require(context, EngineeringCommandPermission.READ)
        async with session.begin():
            review = await self.repository.get_for_update(
                session,
                company_id=context.company.id,
                review_id=review_id,
            )
            if review is None:
                raise EngineeringReviewNotFoundError("Engineering review not found.")
            source = await self.repository.load_package_source(
                session,
                company_id=context.company.id,
                review=review,
            )
            if source is None or self._review_digest(source) != review.review_digest:
                raise EngineeringReviewDigestMismatchError(
                    "Review evidence is unavailable or changed."
                )
            decision = await self.repository.get_decision(
                session,
                company_id=context.company.id,
                review_id=review.id,
            )
            return self._package(review, source, decision)

    async def list(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        state: EngineeringReviewState | None = None,
        limit: int = 50,
    ) -> tuple[EngineeringReviewRecord, ...]:
        self._require(context, EngineeringCommandPermission.READ)
        if not 1 <= limit <= 100:
            raise EngineeringReviewIneligibleError("Review limit is invalid.")
        return await self.repository.list_reviews(
            session,
            company_id=context.company.id,
            state=state,
            limit=limit,
        )

    async def decide(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: DecideEngineeringReview,
        now: datetime | None = None,
    ) -> EngineeringReviewPackage:
        self._require(context, EngineeringCommandPermission.APPROVE)
        reason = command.reason_code.strip() if command.reason_code else None
        if command.decision is EngineeringReviewDecision.REJECT:
            if reason is None or REASON_CODE.fullmatch(reason) is None:
                raise EngineeringReviewIneligibleError(
                    "A controlled rejection reason is required."
                )
        elif reason is not None and REASON_CODE.fullmatch(reason) is None:
            raise EngineeringReviewIneligibleError("Decision reason is invalid.")
        occurred_at = now or utc_now()
        async with session.begin():
            current = await self.repository.get_for_update(
                session,
                company_id=context.company.id,
                review_id=command.review_id,
            )
            if current is None:
                raise EngineeringReviewNotFoundError("Engineering review not found.")
            existing = await self.repository.get_decision(
                session,
                company_id=context.company.id,
                review_id=current.id,
            )
            if existing is not None:
                if (
                    existing.decision is command.decision
                    and existing.review_digest == command.review_digest
                    and existing.reason_code == reason
                ):
                    source = await self._source(session, context, current)
                    return self._package(current, source, existing)
                raise EngineeringReviewConflictError("Review is already decided.")
            if current.review_digest != command.review_digest:
                raise EngineeringReviewDigestMismatchError(
                    "Reviewed evidence is stale."
                )
            if current.version != command.expected_version:
                raise EngineeringReviewConflictError("Review version changed.")
            source = await self._source(session, context, current)
            target = (
                EngineeringReviewState.ACCEPTED
                if command.decision is EngineeringReviewDecision.ACCEPT
                else EngineeringReviewState.REJECTED
            )
            updated = await self.repository.transition(
                session,
                company_id=context.company.id,
                review_id=current.id,
                expected_version=current.version,
                state=target,
                now=occurred_at,
            )
            if updated is None:
                raise EngineeringReviewConflictError("Review version changed.")
            decision = await self.repository.create_decision(
                session,
                review=updated,
                reviewer_user_id=context.user.id,
                decision=command.decision,
                reason_code=reason,
                now=occurred_at,
            )
            self._stage(
                session,
                context=context,
                review=updated,
                event_type=EventType.ENGINEERING_REVIEW_DECIDED,
                action="engineering.review_decided",
                details={
                    "state": updated.state.value,
                    "decision": decision.decision.value,
                    "reason_code": reason,
                },
                now=occurred_at,
            )
            return self._package(updated, source, decision)

    async def _source(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        review: EngineeringReviewRecord,
    ) -> EngineeringReviewSource:
        source = await self.repository.load_package_source(
            session,
            company_id=context.company.id,
            review=review,
        )
        if source is None or self._review_digest(source) != review.review_digest:
            raise EngineeringReviewDigestMismatchError(
                "Review evidence is unavailable or changed."
            )
        return source

    @staticmethod
    def _validate_source(source: EngineeringReviewSource) -> None:
        if source.command.approval_state != "approved":
            raise EngineeringReviewIneligibleError("Command is not approved.")
        if source.attempt.state not in {
            "completed",
            "failed",
            "cancelled",
            "timed_out",
        }:
            raise EngineeringReviewIneligibleError("Execution is not terminal.")
        if source.result.disposition != "accepted":
            raise EngineeringReviewIneligibleError(
                "Quarantined or rejected results cannot enter owner review."
            )
        if source.result.repository_mutated:
            raise EngineeringReviewIneligibleError(
                "Repository-mutating results cannot enter owner review."
            )
        if (
            source.command.instruction_digest != source.composition.instruction_digest
            or source.command.request_digest != source.composition.request_digest
        ):
            raise EngineeringReviewDigestMismatchError(
                "Execution evidence does not match the approved command."
            )
        serialized = json.dumps(
            {
                "evidence": source.result.evidence_summary,
                "validation": source.result.validation_summary,
                "outputs": source.result.output_references,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        if (
            len(serialized) > MAX_REVIEW_JSON_BYTES
            or len(source.result.output_references) > MAX_OUTPUT_REFERENCES
        ):
            raise EngineeringReviewIneligibleError("Review evidence is too large.")

    @staticmethod
    def _review_digest(source: EngineeringReviewSource) -> str:
        return calculate_review_digest(source)

    @staticmethod
    def _package(
        review: EngineeringReviewRecord,
        source: EngineeringReviewSource,
        decision,
    ) -> EngineeringReviewPackage:
        return EngineeringReviewPackage(
            review=review,
            ecid=source.command.ecid,
            command_type=source.command.command_type,
            owner_instruction=source.command.owner_instruction,
            requested_code_changes=source.command.requested_code_changes,
            repository_key=source.command.repository_key,
            expected_branch=source.command.expected_branch,
            expected_head=source.command.expected_head,
            result_status=source.result.status,
            result_disposition=source.result.disposition,
            evidence_summary=dict(source.result.evidence_summary),
            validation_summary=dict(source.result.validation_summary),
            output_references=tuple(source.result.output_references),
            failure_classification=source.result.failure_classification,
            repository_mutated=source.result.repository_mutated,
            result_received_at=source.result.received_at,
            decision=decision,
        )

    def _require(self, context: AuthorizationContext, permission: str) -> None:
        try:
            self.authorization.require_permission(context, permission)
        except PermissionDeniedError as error:
            raise EngineeringReviewNotFoundError(
                "Engineering review not found."
            ) from error

    def _stage(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        review: EngineeringReviewRecord,
        event_type: EventType,
        action: str,
        details: dict[str, object],
        now: datetime,
    ) -> None:
        safe = {
            **details,
            "review_id": str(review.id),
            "command_id": str(review.command_id),
            "execution_id": str(review.execution_id),
            "provider_identifier": review.provider_identifier,
            "review_digest": review.review_digest,
            "version": review.version,
        }
        self.audit.stage(
            session,
            AuditEntry(
                action=action,
                resource_type="engineering_execution_review",
                company_id=context.company.id,
                resource_id=review.id,
                details=safe,
                occurred_at=now,
            ),
        )
        self.events.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="engineering_execution_review",
                entity_id=review.id,
                company_id=context.company.id,
                payload=safe,
                occurred_at=now,
            ),
        )


engineering_review_service = EngineeringReviewService()

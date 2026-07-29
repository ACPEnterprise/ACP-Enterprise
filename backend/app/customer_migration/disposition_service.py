import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from app.customer_migration.disposition_contracts import (
    DISPOSITION_IDENTITY_VERSION,
    DISPOSITION_REPLAY_VERSION,
    DispositionApplicationReceipt,
    DispositionAuditMetadata,
    DispositionDecision,
    DispositionReplayApplication,
    DispositionReplayPlan,
    DispositionSourceIdentity,
    OwnerDisposition,
    disposition_identity,
    owner_disposition_record_sha256,
)
from app.customer_migration.disposition_repository import (
    DispositionApplicationLedger,
    OwnerDispositionRepository,
)
from app.platform.permissions.authorization import AuthorizationContext


class DispositionError(ValueError):
    pass


class DispositionOwnershipError(DispositionError):
    pass


class OwnerApprovalRequiredError(DispositionError):
    pass


class DispositionVersionConflictError(DispositionError):
    pass


class DispositionIntegrityError(DispositionError):
    pass


class OwnerApprovalVerifier(Protocol):
    async def is_explicit_owner_approval(
        self,
        *,
        context: AuthorizationContext,
        approval_request_id: UUID,
        approval_evidence_sha256: str,
    ) -> bool: ...


class DispositionEffectPort(Protocol):
    """Apply by application_id idempotently and return a deterministic digest."""

    async def apply(self, application: DispositionReplayApplication) -> str: ...


@dataclass(frozen=True)
class ApproveDisposition:
    source: DispositionSourceIdentity
    subject_key: str
    decision: DispositionDecision
    expected_previous_version: int
    approved_by_user_id: UUID
    approved_at: datetime
    reason_code: str
    approval_request_id: UUID
    approval_evidence_sha256: str


@dataclass(frozen=True)
class ReplayApplicationResult:
    receipt: DispositionApplicationReceipt
    reused: bool


def _sha256(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _replay_order(disposition: OwnerDisposition) -> tuple[str, str, str, int, str]:
    return (
        disposition.source.source_identity_sha256,
        disposition.decision.kind.value,
        disposition.subject_key,
        disposition.version,
        str(disposition.id),
    )


class OwnerDispositionService:
    def __init__(
        self,
        *,
        repository: OwnerDispositionRepository,
        owner_approval: OwnerApprovalVerifier,
    ) -> None:
        self.repository = repository
        self.owner_approval = owner_approval

    async def approve(
        self,
        *,
        context: AuthorizationContext,
        command: ApproveDisposition,
        disposition_id: UUID | None = None,
    ) -> OwnerDisposition:
        self._require_company(context, command.source.company_id)
        if command.approved_by_user_id != context.user.id:
            raise DispositionOwnershipError(
                "approval actor must match the authenticated owner context"
            )
        if command.expected_previous_version < 0:
            raise DispositionVersionConflictError(
                "expected_previous_version must be nonnegative"
            )
        approved = await self.owner_approval.is_explicit_owner_approval(
            context=context,
            approval_request_id=command.approval_request_id,
            approval_evidence_sha256=command.approval_evidence_sha256,
        )
        if not approved:
            raise OwnerApprovalRequiredError(
                "an explicit owner approval record is required"
            )
        identity = disposition_identity(
            source=command.source,
            kind=command.decision.kind,
            subject_key=command.subject_key,
        )
        latest = await self.repository.get_latest(
            company_id=context.company.id,
            disposition_identity=identity,
        )
        actual_previous_version = latest.version if latest else 0
        if actual_previous_version != command.expected_previous_version:
            raise DispositionVersionConflictError(
                "disposition changed after the owner reviewed it"
            )
        audit = DispositionAuditMetadata(
            approved_by_user_id=command.approved_by_user_id,
            approved_at=command.approved_at,
            reason_code=command.reason_code,
            approval_request_id=command.approval_request_id,
            approval_evidence_sha256=command.approval_evidence_sha256,
        )
        new_id = disposition_id or uuid4()
        version = actual_previous_version + 1
        record_sha256 = owner_disposition_record_sha256(
            disposition_id=new_id,
            disposition_identity_value=identity,
            version=version,
            source=command.source,
            subject_key=command.subject_key,
            decision=command.decision,
            audit=audit,
            prior_disposition_id=latest.id if latest else None,
        )
        disposition = OwnerDisposition(
            id=new_id,
            identity_version=DISPOSITION_IDENTITY_VERSION,
            disposition_identity=identity,
            version=version,
            source=command.source,
            subject_key=command.subject_key,
            decision=command.decision,
            audit=audit,
            prior_disposition_id=latest.id if latest else None,
            record_sha256=record_sha256,
        )
        return await self.repository.append(
            disposition,
            expected_previous_version=command.expected_previous_version,
        )

    async def replay_plan(
        self,
        *,
        context: AuthorizationContext,
        source_artifact_sha256: str,
    ) -> DispositionReplayPlan:
        stored = await self.repository.list_for_replay(
            company_id=context.company.id,
            source_artifact_sha256=source_artifact_sha256,
        )
        latest: dict[str, OwnerDisposition] = {}
        for disposition in stored:
            self._require_company(context, disposition.source.company_id)
            if disposition.source.source_artifact_sha256 != source_artifact_sha256:
                raise DispositionIntegrityError(
                    "repository returned a disposition for another source artifact"
                )
            prior = latest.get(disposition.disposition_identity)
            if prior is None or disposition.version > prior.version:
                latest[disposition.disposition_identity] = disposition
            elif disposition.version == prior.version and disposition != prior:
                raise DispositionIntegrityError(
                    "conflicting immutable disposition versions were returned"
                )
        ordered = sorted(latest.values(), key=_replay_order)
        applications = tuple(
            DispositionReplayApplication(
                replay_version=DISPOSITION_REPLAY_VERSION,
                ordinal=ordinal,
                application_id=_sha256(
                    {
                        "replay_version": DISPOSITION_REPLAY_VERSION,
                        "company_id": str(context.company.id),
                        "source_artifact_sha256": source_artifact_sha256,
                        "ordinal": ordinal,
                        "disposition_record_sha256": disposition.record_sha256,
                    }
                ),
                disposition=disposition,
            )
            for ordinal, disposition in enumerate(ordered)
        )
        replay_sha256 = _sha256(
            {
                "replay_version": DISPOSITION_REPLAY_VERSION,
                "company_id": str(context.company.id),
                "source_artifact_sha256": source_artifact_sha256,
                "applications": [item.application_id for item in applications],
            }
        )
        return DispositionReplayPlan(
            replay_version=DISPOSITION_REPLAY_VERSION,
            company_id=context.company.id,
            source_artifact_sha256=source_artifact_sha256,
            applications=applications,
            replay_sha256=replay_sha256,
        )

    @staticmethod
    def _require_company(context: AuthorizationContext, company_id: UUID) -> None:
        if (
            context.company.id != company_id
            or context.membership.company_id != company_id
        ):
            raise DispositionOwnershipError(
                "disposition must remain within the authenticated Company"
            )


class DispositionReplayService:
    def __init__(
        self,
        *,
        ledger: DispositionApplicationLedger,
        effect_port: DispositionEffectPort,
    ) -> None:
        self.ledger = ledger
        self.effect_port = effect_port

    async def apply(
        self,
        *,
        context: AuthorizationContext,
        plan: DispositionReplayPlan,
        applied_at: datetime,
    ) -> tuple[ReplayApplicationResult, ...]:
        if plan.company_id != context.company.id:
            raise DispositionOwnershipError("replay plan belongs to another Company")
        results: list[ReplayApplicationResult] = []
        for application in plan.applications:
            if application.disposition.source.company_id != context.company.id:
                raise DispositionOwnershipError(
                    "replay application belongs to another Company"
                )
            prior = await self.ledger.get_receipt(
                company_id=context.company.id,
                application_id=application.application_id,
            )
            if prior is not None:
                if (
                    prior.disposition_record_sha256
                    != application.disposition.record_sha256
                ):
                    raise DispositionIntegrityError(
                        "application identity was reused with different content"
                    )
                results.append(ReplayApplicationResult(prior, reused=True))
                continue
            effect_sha256 = await self.effect_port.apply(application)
            receipt = DispositionApplicationReceipt(
                company_id=context.company.id,
                application_id=application.application_id,
                disposition_record_sha256=application.disposition.record_sha256,
                effect_sha256=effect_sha256,
                applied_at=applied_at,
            )
            stored = await self.ledger.record_receipt(receipt)
            results.append(ReplayApplicationResult(stored, reused=False))
        return tuple(results)

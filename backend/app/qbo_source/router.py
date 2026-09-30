from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.database.session import AsyncSessionFactory
from app.platform.auth.errors import RateLimitExceededError, RateLimitUnavailableError
from app.platform.auth.rate_limit import AuthenticationRateLimiter
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    AccountingPermission,
    AdministrationPermission,
)
from app.platform.permissions.dependencies import require_permission

from .accounting_evidence_projection import (
    Basis,
    QboEvidenceProjectionError,
    project_latest_qbo_workspace,
    unavailable_qbo_workspace,
)
from .application_models import (
    QboNativeApplicationRecord,
    QboNativeReviewDecision,
    QboNativeReviewItem,
)
from .bounded_evidence import (
    BoundedEvidenceError,
    latest_bounded_evidence,
    load_bounded_envelopes,
)
from .callback import CALLBACK_PATH
from .intuit import IntuitAuthenticationError, IntuitError, IntuitProtocolError
from .native_application import (
    FamilyDispositionCount,
    QboApplicationError,
    ReviewDecisionCommand,
    qbo_native_application_service,
    review_action_authority,
)
from .production import (
    ProductionAgedReceivablesRequest,
    ProductionProfitAndLossRequest,
    read_production_aged_receivables,
    read_production_profit_and_loss,
)
from .runtime import (
    SandboxRuntimeError,
    get_production_oauth_runtime,
    get_sandbox_oauth_runtime,
)
from .secrets import SandboxSecretStoreError
from .source_report import project_aged_receivables, project_profit_and_loss

router = APIRouter(tags=["QBO Sandbox OAuth"])
_rate_limiter = AuthenticationRateLimiter()
_Administer = Annotated[
    AuthorizationContext,
    Depends(require_permission(AdministrationPermission.COMPANY_ADMINISTER)),
]
_ReportRead = Annotated[
    AuthorizationContext,
    Depends(require_permission(AccountingPermission.REPORT_READ)),
]
_Reconcile = Annotated[
    AuthorizationContext,
    Depends(require_permission(AccountingPermission.RECONCILE)),
]


def get_qbo_application_session_factory() -> async_sessionmaker[AsyncSession]:
    return AsyncSessionFactory


_ApplicationFactory = Annotated[
    async_sessionmaker[AsyncSession], Depends(get_qbo_application_session_factory)
]

AUTHORIZE_PATH = "/api/v1/integrations/qbo/oauth/authorize"
CONNECTION_PATH = "/api/v1/integrations/qbo/connection"
DISCONNECT_PATH = "/api/v1/integrations/qbo/oauth/disconnect"
_CALLBACK_URI = (
    "https://preview.allcountyhomeservices.com/api/v1/integrations/qbo/oauth/callback"
)
PRODUCTION_AUTHORIZE_PATH = "/api/v1/integrations/qbo/production/oauth/authorize"
PRODUCTION_CONNECTION_PATH = "/api/v1/integrations/qbo/production/connection"
PRODUCTION_CALLBACK_PATH = "/api/v1/integrations/qbo/production/oauth/callback"
ACCOUNTING_EVIDENCE_PATH = "/api/v1/accounting/source-evidence/qbo"
PROFIT_AND_LOSS_PATH = "/api/v1/accounting/source-evidence/qbo/reports/profit-and-loss"
AGED_RECEIVABLES_PATH = (
    "/api/v1/accounting/source-evidence/qbo/reports/aged-receivables"
)
NATIVE_APPLICATION_PATH = "/api/v1/accounting/source-evidence/qbo/native-application"
NATIVE_REVIEW_PATH = f"{NATIVE_APPLICATION_PATH}/review-queue"


class QboReviewDecisionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=4, max_length=1000)
    target_native_id: UUID | None = None
    evidence_reference: str | None = Field(default=None, max_length=240)
    supersedes_decision_id: UUID | None = None


_PRODUCTION_CALLBACK_URI = (
    "https://preview.allcountyhomeservices.com"
    "/api/v1/integrations/qbo/production/oauth/callback"
)

_SAFE_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
}


def _family_count_response(item: FamilyDispositionCount) -> dict[str, object]:
    return {
        "source_family": item.source_family,
        "total_source": item.total,
        "applied": item.applied,
        "bound": item.bound,
        "quarantined": item.quarantined,
        "provider_unavailable": item.provider_unavailable,
        "unsupported": item.unsupported,
        "rejected": item.rejected,
        "unexplained": item.unexplained,
        "safe_majority_applied_percentage": item.safe_majority_applied_percentage,
    }


def _sealed_evidence_readiness(
    authorization: AuthorizationContext,
) -> dict[str, object]:
    if (
        not settings.qbo_production_acp_company_id
        or settings.qbo_production_acp_company_id != authorization.company.id
        or not settings.qbo_production_evidence_root
    ):
        return {
            "available": False,
            "reason": "Production source custody is not configured for this Company.",
        }
    try:
        packet = latest_bounded_evidence(Path(settings.qbo_production_evidence_root))
        if packet is None:
            return {
                "available": False,
                "reason": "No complete sealed QuickBooks acquisition is available.",
            }
        envelopes = load_bounded_envelopes(packet)
        families = Counter(
            envelope.native_entity_type.lower() for _, envelope in envelopes
        )
        return {
            "available": True,
            "reason": None,
            "source_run_id": packet.manifest.get("run_id"),
            "source_manifest_sha256": packet.manifest_sha256,
            "acquired_at": packet.manifest.get("ended_at"),
            "total_source_records": len(envelopes),
            "source_families": [
                {"source_family": family, "total_source": total}
                for family, total in sorted(families.items())
            ],
        }
    except (KeyError, OSError, ValueError, BoundedEvidenceError):
        return {
            "available": False,
            "reason": "Sealed QuickBooks evidence failed custody or digest validation.",
        }


@router.post(NATIVE_APPLICATION_PATH, name="qbo-native-clean-majority-application")
async def apply_qbo_native_clean_majority(
    authorization: _Reconcile,
    factory: _ApplicationFactory,
) -> JSONResponse:
    """Apply sealed QBO evidence only; never call or mutate QuickBooks."""
    if (
        not settings.qbo_production_acp_company_id
        or settings.qbo_production_acp_company_id != authorization.company.id
        or not settings.qbo_production_evidence_root
    ):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "Sealed QBO Production evidence is unavailable."},
            headers={"Cache-Control": "private, no-store"},
        )
    try:
        packet = latest_bounded_evidence(Path(settings.qbo_production_evidence_root))
        if packet is None:
            raise BoundedEvidenceError("bounded_source_unavailable")
        catalog_dispositions = packet.manifest.get("catalog_dispositions", [])
        if not isinstance(catalog_dispositions, list):
            raise BoundedEvidenceError("bounded_catalog_dispositions_invalid")
        acquired_at = datetime.fromisoformat(str(packet.manifest["ended_at"]))
        for disposition in catalog_dispositions:
            if not isinstance(disposition, Mapping):
                raise BoundedEvidenceError("bounded_catalog_dispositions_invalid")
            state = str(disposition.get("disposition", ""))
            family = str(disposition.get("entity_kind", ""))
            if "UNAVAILABLE" not in state or not family:
                continue
            encoded = json.dumps(
                dict(disposition), sort_keys=True, separators=(",", ":")
            ).encode()
            await qbo_native_application_service.record_provider_unavailable(
                factory,
                context=authorization,
                realm_id=str(packet.bounded_manifest["realm_id"]),
                source_family=family,
                reason_code="provider_family_unavailable",
                explanation=(
                    "QuickBooks did not provide this source family in the sealed "
                    "bounded acquisition."
                ),
                evidence_digest=hashlib.sha256(encoded).hexdigest(),
                acquired_at=acquired_at,
            )
        result = await qbo_native_application_service.apply_clean_majority(
            factory,
            context=authorization,
            envelopes=load_bounded_envelopes(packet),
        )
    except (KeyError, OSError, ValueError, BoundedEvidenceError, QboApplicationError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "Sealed QBO evidence could not be applied safely."},
            headers={"Cache-Control": "private, no-store"},
        )
    return JSONResponse(
        content={
            "classification": "QBO_NATIVE_CLEAN_MAJORITY_PROCESSED",
            "source_run_id": packet.manifest.get("run_id"),
            "source_manifest_sha256": packet.manifest_sha256,
            "processed": result.processed,
            "created": result.created,
            "replayed": result.replayed,
            "families": [_family_count_response(item) for item in result.family_counts],
            "qbo_write_performed": False,
            "accounting_posting_performed": False,
        },
        headers={"Cache-Control": "private, no-store"},
    )


@router.get(NATIVE_APPLICATION_PATH, name="qbo-native-application-ledger")
async def qbo_native_application_ledger(
    authorization: _Reconcile,
    factory: _ApplicationFactory,
) -> JSONResponse:
    counts = await qbo_native_application_service.family_counts(
        factory, context=authorization
    )
    summary = await qbo_native_application_service.ledger_summary(
        factory, context=authorization
    )
    return JSONResponse(
        content={
            "source_evidence": _sealed_evidence_readiness(authorization),
            "families": [_family_count_response(item) for item in counts],
            "last_execution": {
                "total_dispositions": summary.total_dispositions,
                "last_applied_at": (
                    summary.last_applied_at.isoformat()
                    if summary.last_applied_at is not None
                    else None
                ),
            },
            "qbo_write_performed": False,
            "accounting_posting_performed": False,
        },
        headers={"Cache-Control": "private, no-store"},
    )


@router.get(NATIVE_REVIEW_PATH, name="qbo-native-review-queue")
async def qbo_native_review_queue(
    authorization: _Reconcile,
    factory: _ApplicationFactory,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> JSONResponse:
    items = await qbo_native_application_service.open_review_items(
        factory, context=authorization, limit=limit
    )
    application_ids = [item.application_record_id for item in items]
    async with factory() as session:
        records = {
            record.id: record
            for record in (
                await session.scalars(
                    select(QboNativeApplicationRecord).where(
                        QboNativeApplicationRecord.company_id
                        == authorization.company.id,
                        QboNativeApplicationRecord.id.in_(application_ids),
                    )
                )
            ).all()
        }
        decisions = {
            decision.review_item_id: decision
            for decision in (
                await session.scalars(
                    select(QboNativeReviewDecision).where(
                        QboNativeReviewDecision.company_id == authorization.company.id,
                        QboNativeReviewDecision.review_item_id.in_(
                            [item.id for item in items]
                        ),
                        QboNativeReviewDecision.superseded_at.is_(None),
                    )
                )
            ).all()
        }
    return JSONResponse(
        content={
            "items": [
                {
                    "id": str(item.id),
                    "source_family": item.source_family,
                    "provider_record_id": item.provider_record_id,
                    "provider_version": (
                        records[item.application_record_id].provider_version
                        if item.application_record_id in records
                        else None
                    ),
                    "reference_number": item.reference_number,
                    "source_date": item.source_date,
                    "source_amount": item.source_amount,
                    "source_entity_names": item.source_entity_names,
                    "candidate_native_ids": item.candidate_native_ids,
                    "conflicting_fields": item.conflicting_fields,
                    "exact_conflict": item.exact_conflict,
                    "affected_dependents": item.affected_dependents,
                    "allowed_actions": [
                        {
                            "action": action,
                            "required_authority": review_action_authority(action),
                        }
                        for action in item.allowed_actions
                    ],
                    "current_decision": (
                        {
                            "id": str(decisions[item.id].id),
                            "action": decisions[item.id].action,
                            "authority_class": decisions[item.id].authority_class,
                            "reason": decisions[item.id].reason,
                            "decided_at": decisions[item.id].decided_at.isoformat(),
                        }
                        if item.id in decisions
                        else None
                    ),
                    "state": item.state,
                    "unlocks": len(item.affected_dependents),
                }
                for item in items
            ]
        },
        headers={"Cache-Control": "private, no-store"},
    )


@router.post(
    f"{NATIVE_REVIEW_PATH}/{{review_item_id}}/decisions",
    name="qbo-native-review-decision",
)
async def decide_qbo_native_review(
    review_item_id: UUID,
    command: QboReviewDecisionRequest,
    authorization: _Reconcile,
    factory: _ApplicationFactory,
) -> JSONResponse:
    try:
        decision = await qbo_native_application_service.decide_review(
            factory,
            context=authorization,
            review_item_id=review_item_id,
            command=ReviewDecisionCommand(
                action=command.action,
                reason=command.reason,
                target_native_id=command.target_native_id,
                evidence_reference=command.evidence_reference,
                supersedes_decision_id=command.supersedes_decision_id,
            ),
        )
    except QboApplicationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    re_evaluated = 0
    if settings.qbo_production_evidence_root:
        async with factory() as session:
            item = await session.scalar(
                select(QboNativeReviewItem).where(
                    QboNativeReviewItem.id == review_item_id,
                    QboNativeReviewItem.company_id == authorization.company.id,
                )
            )
        if item is not None and item.affected_dependents:
            try:
                packet = latest_bounded_evidence(
                    Path(settings.qbo_production_evidence_root)
                )
                if packet is not None:
                    dependent_ids = set(item.affected_dependents)
                    bounded = tuple(
                        value
                        for value in load_bounded_envelopes(packet)
                        if value[1].native_id in dependent_ids
                    )
                    if bounded:
                        replay = (
                            await qbo_native_application_service.apply_clean_majority(
                                factory, context=authorization, envelopes=bounded
                            )
                        )
                        re_evaluated = replay.processed
            except (
                KeyError,
                OSError,
                ValueError,
                BoundedEvidenceError,
                QboApplicationError,
            ):
                re_evaluated = 0
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "decision_id": str(decision.id),
            "review_item_id": str(decision.review_item_id),
            "action": decision.action,
            "authority_class": decision.authority_class,
            "decided_at": decision.decided_at.isoformat(),
            "dependent_records_re_evaluated": re_evaluated,
            "qbo_write_performed": False,
            "accounting_posting_performed": False,
        },
        headers={"Cache-Control": "private, no-store"},
    )


@router.get(ACCOUNTING_EVIDENCE_PATH, name="qbo-accounting-source-evidence")
async def qbo_accounting_source_evidence(
    basis: Basis,
    authorization: _ReportRead,
) -> JSONResponse:
    """Return sealed QBO evidence; never query QBO or create Accounting truth."""
    if (
        not settings.qbo_production_acp_company_id
        or settings.qbo_production_acp_company_id != authorization.company.id
    ):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "QBO source evidence is not available."},
            headers={"Cache-Control": "private, no-store"},
        )
    if not settings.qbo_production_evidence_root:
        workspace = unavailable_qbo_workspace(
            basis=basis, limitation="live_qbo_authorization_blocked"
        )
    else:
        try:
            workspace = project_latest_qbo_workspace(
                evidence_root=Path(settings.qbo_production_evidence_root),
                basis=basis,
                runtime_root=(
                    Path(settings.qbo_production_runtime_root)
                    if settings.qbo_production_runtime_root
                    else None
                ),
            )
        except (OSError, ValueError, QboEvidenceProjectionError):
            workspace = unavailable_qbo_workspace(
                basis=basis, limitation="protected_qbo_evidence_invalid"
            )
    return JSONResponse(
        content=workspace, headers={"Cache-Control": "private, no-store"}
    )


@router.get(PROFIT_AND_LOSS_PATH, name="qbo-source-backed-profit-and-loss")
async def qbo_source_backed_profit_and_loss(
    start_date: date,
    end_date: date,
    basis: Basis,
    authorization: _ReportRead,
) -> JSONResponse:
    """Read a real-company provider P&L without creating ACP ledger truth."""
    if (
        not settings.qbo_production_acp_company_id
        or settings.qbo_production_acp_company_id != authorization.company.id
    ):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "QBO source report is not available."},
            headers={"Cache-Control": "private, no-store"},
        )
    if start_date > end_date:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "Report start date must not follow end date."},
            headers={"Cache-Control": "private, no-store"},
        )
    try:
        document, marker = await read_production_profit_and_loss(
            ProductionProfitAndLossRequest(start_date, end_date, basis)
        )
        workspace = project_profit_and_loss(
            document,
            realm_id=str(marker["realm_id"]),
            expected_company_name=str(marker["company_name"]),
        )
    except (
        OSError,
        ValueError,
        QboEvidenceProjectionError,
        SandboxRuntimeError,
        SandboxSecretStoreError,
        IntuitError,
    ):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "QBO source report is temporarily unavailable."},
            headers={"Cache-Control": "private, no-store"},
        )
    return JSONResponse(
        content=workspace, headers={"Cache-Control": "private, no-store"}
    )


@router.get(AGED_RECEIVABLES_PATH, name="qbo-source-backed-aged-receivables")
async def qbo_source_backed_aged_receivables(
    report_date: date,
    authorization: _ReportRead,
) -> JSONResponse:
    """Read QBO's net A/R aging total without creating ACP Accounting truth."""
    if (
        not settings.qbo_production_acp_company_id
        or settings.qbo_production_acp_company_id != authorization.company.id
    ):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "QBO source report is not available."},
            headers={"Cache-Control": "private, no-store"},
        )
    try:
        document, marker = await read_production_aged_receivables(
            ProductionAgedReceivablesRequest(report_date)
        )
        workspace = project_aged_receivables(
            document,
            realm_id=str(marker["realm_id"]),
            expected_company_name=str(marker["company_name"]),
        )
    except (
        OSError,
        ValueError,
        QboEvidenceProjectionError,
        SandboxRuntimeError,
        SandboxSecretStoreError,
        IntuitError,
    ):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "QBO A/R summary is temporarily unavailable."},
            headers={"Cache-Control": "private, no-store"},
        )
    return JSONResponse(
        content=workspace, headers={"Cache-Control": "private, no-store"}
    )


def _safe_response(status_code: int, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": "sandbox_oauth_callback", "result": code},
        headers=_SAFE_HEADERS,
    )


def _connection_response(status_code: int, connection_state: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "qbo_sandbox_connection",
            "connection_state": connection_state,
        },
        headers=_SAFE_HEADERS,
    )


def _production_response(status_code: int, result: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": "qbo_production_oauth_callback", "result": result},
        headers=_SAFE_HEADERS,
    )


@router.get(PRODUCTION_CONNECTION_PATH, name="qbo-production-connection-evidence")
async def qbo_production_connection_evidence(
    authorization: _Administer,
) -> JSONResponse:
    """Expose safe production authority/readability evidence; never query QBO."""
    del authorization
    try:
        evidence = await get_production_oauth_runtime().connection_evidence()
    except (SandboxRuntimeError, SandboxSecretStoreError, OSError, ValueError):
        evidence = {
            "connection_state": "unavailable",
            "provider_environment": "production",
            "company_identity_sha256": None,
            "company_info_verified_at": None,
            "company_info_readability": "unverified",
            "credential_state": "unverified",
            "token_realm_binding": "unverified",
            "refresh_authority": "unverified",
            "acquisition_eligible": False,
        }
    return JSONResponse(
        content={
            "status": "qbo_production_connection",
            **evidence,
            "mutation_authority": "none",
        },
        headers={"Cache-Control": "private, no-store"},
    )


@router.post(PRODUCTION_AUTHORIZE_PATH, name="qbo-production-oauth-authorize")
async def qbo_production_oauth_authorize(
    authorization: _Administer,
) -> JSONResponse:
    identifier = hashlib.sha256(str(authorization.user.id).encode()).hexdigest()
    try:
        await _rate_limiter.enforce(
            bucket="qbo-production-oauth-initiation",
            identifier_hash=identifier,
            limit=1,
            window_seconds=900,
        )
        authorization_url = await get_production_oauth_runtime().begin(
            redirect_uri=_PRODUCTION_CALLBACK_URI
        )
    except RateLimitExceededError:
        return _production_response(
            status.HTTP_429_TOO_MANY_REQUESTS, "initiation_limited"
        )
    except (
        RateLimitUnavailableError,
        SandboxRuntimeError,
        SandboxSecretStoreError,
        ValueError,
    ):
        return _production_response(
            status.HTTP_503_SERVICE_UNAVAILABLE, "production_not_configured"
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "qbo_production_oauth_initiation",
            "authorization_url": authorization_url,
        },
        headers=_SAFE_HEADERS,
    )


@router.get(PRODUCTION_CALLBACK_PATH, name="qbo-production-oauth-callback")
async def qbo_production_oauth_callback(
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    realm_id: Annotated[str | None, Query(alias="realmId")] = None,
    provider_error: Annotated[str | None, Query(alias="error")] = None,
    internal_code: Annotated[str | None, Header(alias="X-ACP-QBO-Code")] = None,
    internal_state: Annotated[str | None, Header(alias="X-ACP-QBO-State")] = None,
    internal_realm: Annotated[str | None, Header(alias="X-ACP-QBO-Realm")] = None,
    internal_error: Annotated[str | None, Header(alias="X-ACP-QBO-Error")] = None,
) -> JSONResponse:
    code = internal_code or code
    state = internal_state or state
    realm_id = internal_realm or realm_id
    provider_error = internal_error or provider_error
    if not state or (not provider_error and not all((code, realm_id))):
        return _production_response(
            status.HTTP_400_BAD_REQUEST, "connection_not_completed"
        )
    try:
        await get_production_oauth_runtime().complete(
            code=code, state=state, realm_id=realm_id, provider_error=provider_error
        )
    except (SandboxRuntimeError, SandboxSecretStoreError):
        return _production_response(
            status.HTTP_503_SERVICE_UNAVAILABLE, "production_not_configured"
        )
    except (IntuitAuthenticationError, IntuitProtocolError) as error:
        return _production_response(
            status.HTTP_400_BAD_REQUEST, _safe_callback_error(error)
        )
    except Exception:  # noqa: BLE001
        return _production_response(
            status.HTTP_502_BAD_GATEWAY, "provider_verification_failed"
        )
    return _production_response(status.HTTP_200_OK, "connection_completed")


@router.get(CONNECTION_PATH, name="qbo-sandbox-connection-status")
async def qbo_sandbox_connection_status(
    authorization: _Administer,
) -> JSONResponse:
    del authorization
    try:
        state = get_sandbox_oauth_runtime().connection_state()
    except (SandboxRuntimeError, SandboxSecretStoreError):
        return _connection_response(status.HTTP_503_SERVICE_UNAVAILABLE, "unavailable")
    return _connection_response(status.HTTP_200_OK, state)


@router.post(DISCONNECT_PATH, name="qbo-sandbox-oauth-disconnect")
async def qbo_sandbox_oauth_disconnect(
    authorization: _Administer,
) -> JSONResponse:
    identifier = hashlib.sha256(str(authorization.user.id).encode()).hexdigest()
    try:
        await _rate_limiter.enforce(
            bucket="qbo-sandbox-oauth-disconnect",
            identifier_hash=identifier,
            limit=2,
            window_seconds=600,
        )
        state = await get_sandbox_oauth_runtime().disconnect()
    except RateLimitExceededError:
        return _connection_response(
            status.HTTP_429_TOO_MANY_REQUESTS, "disconnect_failed"
        )
    except RateLimitUnavailableError:
        return _connection_response(
            status.HTTP_503_SERVICE_UNAVAILABLE, "disconnect_failed"
        )
    except (IntuitAuthenticationError, IntuitProtocolError):
        return _connection_response(status.HTTP_502_BAD_GATEWAY, "disconnect_failed")
    except (SandboxRuntimeError, SandboxSecretStoreError, OSError, ValueError):
        return _connection_response(
            status.HTTP_503_SERVICE_UNAVAILABLE, "disconnect_failed"
        )
    return _connection_response(status.HTTP_200_OK, state)


def _safe_callback_error(error: IntuitAuthenticationError | IntuitProtocolError) -> str:
    if error.code == "oauth_state_expired":
        return "state_expired"
    if error.code == "oauth_state_replayed":
        return "state_replayed"
    if error.code == "oauth_provider_rejected":
        return "provider_rejected"
    if error.code.startswith(("oauth_state", "oauth_environment")):
        return "state_invalid"
    if error.code.startswith("token_") or error.code == "invalid_token_response":
        return "token_exchange_failed"
    if error.code == "company_realm_mismatch":
        return "realm_mismatch"
    if error.code == "company_identity_mismatch":
        return "company_name_mismatch"
    if error.code.startswith("company_info"):
        return "companyinfo_failed"
    return "provider_verification_failed"


@router.post(AUTHORIZE_PATH, name="qbo-sandbox-oauth-authorize")
async def qbo_sandbox_oauth_authorize(
    request: Request,
    authorization: _Administer,
) -> JSONResponse:
    """Create protected state and return one sandbox authorization URL."""
    del request
    identifier = hashlib.sha256(str(authorization.user.id).encode()).hexdigest()
    try:
        await _rate_limiter.enforce(
            bucket="qbo-sandbox-oauth-initiation",
            identifier_hash=identifier,
            limit=3,
            window_seconds=600,
        )
        authorization_url = await get_sandbox_oauth_runtime().begin(
            redirect_uri=_CALLBACK_URI
        )
    except RateLimitExceededError:
        return _safe_response(status.HTTP_429_TOO_MANY_REQUESTS, "initiation_limited")
    except RateLimitUnavailableError:
        return _safe_response(
            status.HTTP_503_SERVICE_UNAVAILABLE, "initiation_safeguard_unavailable"
        )
    except (SandboxRuntimeError, SandboxSecretStoreError, ValueError):
        return _safe_response(
            status.HTTP_503_SERVICE_UNAVAILABLE, "sandbox_not_configured"
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "sandbox_oauth_initiation",
            "authorization_url": authorization_url,
        },
        headers=_SAFE_HEADERS,
    )


@router.get(CALLBACK_PATH, name="qbo-sandbox-oauth-callback")
async def qbo_sandbox_oauth_callback(
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    realm_id: Annotated[str | None, Query(alias="realmId")] = None,
    provider_error: Annotated[str | None, Query(alias="error")] = None,
    error_description: Annotated[str | None, Query()] = None,
    internal_code: Annotated[str | None, Header(alias="X-ACP-QBO-Code")] = None,
    internal_state: Annotated[str | None, Header(alias="X-ACP-QBO-State")] = None,
    internal_realm: Annotated[str | None, Header(alias="X-ACP-QBO-Realm")] = None,
    internal_error: Annotated[str | None, Header(alias="X-ACP-QBO-Error")] = None,
) -> JSONResponse:
    del error_description
    effective_code = internal_code or code
    effective_state = internal_state or state
    effective_realm = internal_realm or realm_id
    effective_error = internal_error or provider_error
    if not effective_state or (
        not effective_error and not all((effective_code, effective_realm))
    ):
        return _safe_response(status.HTTP_400_BAD_REQUEST, "connection_not_completed")
    try:
        runtime = get_sandbox_oauth_runtime()
        await runtime.complete(
            code=effective_code,
            state=effective_state,
            realm_id=effective_realm,
            provider_error=effective_error,
        )
    except (SandboxRuntimeError, SandboxSecretStoreError):
        return _safe_response(
            status.HTTP_503_SERVICE_UNAVAILABLE, "sandbox_not_configured"
        )
    except (IntuitAuthenticationError, IntuitProtocolError) as error:
        return _safe_response(status.HTTP_400_BAD_REQUEST, _safe_callback_error(error))
    except ValueError:
        return _safe_response(
            status.HTTP_400_BAD_REQUEST, "provider_verification_failed"
        )
    except Exception:  # noqa: BLE001 - external boundary returns no sensitive detail
        return _safe_response(
            status.HTTP_502_BAD_GATEWAY, "provider_verification_failed"
        )
    return _safe_response(status.HTTP_200_OK, "connection_completed")

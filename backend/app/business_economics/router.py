from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.operational_measurement.foundation import (
    CONTRACT_VERSION as MEASUREMENT_VERSION,
)
from app.operational_measurement.foundation import (
    source_matrix as operational_measurement_source_matrix,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    AccountingPermission,
    AccountsPayablePermission,
    AssetPermission,
    CommunicationsPermission,
    EconomicsPolicyPermission,
    InvoicePermission,
    PaymentPermission,
    WorkforcePermission,
)
from app.platform.permissions.dependencies import (
    require_all_permissions,
    require_permission,
)
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

from .capability_readiness import capability_readiness_matrix
from .cash_operational_service import CashOperationalEconomicsService
from .operational_sources import OperationalSourceEconomicsService
from .owner_intelligence import (
    OwnerIntelligenceQuery,
    OwnerIntelligenceService,
    OwnerQuestion,
)
from .policy_administration import EconomicsPolicyAdministrationService
from .result_history import EconomicsResultHistoryError, EconomicsResultHistoryService
from .source_completeness import source_completeness_matrix
from .workspace import EconomicsWorkspaceService

router = APIRouter(prefix="/api/v1/business-economics", tags=["Business Economics"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
Reader = Annotated[
    AuthorizationContext,
    Depends(require_permission(EconomicsPolicyPermission.MEASUREMENT_READ)),
]
PolicyReader = Annotated[
    AuthorizationContext,
    Depends(require_permission(EconomicsPolicyPermission.READ)),
]
CashOperationalReader = Annotated[
    AuthorizationContext,
    Depends(
        require_all_permissions(
            EconomicsPolicyPermission.MEASUREMENT_READ,
            InvoicePermission.READ,
            PaymentPermission.READ,
            AccountsPayablePermission.REPORT_READ,
            AccountingPermission.REPORT_READ,
        )
    ),
]
OperationalSourceReader = Annotated[
    AuthorizationContext,
    Depends(
        require_all_permissions(
            EconomicsPolicyPermission.MEASUREMENT_READ,
            AssetPermission.READ,
            WorkforcePermission.READ,
            CommunicationsPermission.READ,
            AccountingPermission.REPORT_READ,
        )
    ),
]


@router.get("/capabilities", response_model=dict[str, object])
async def economics_capabilities(context: Reader) -> dict[str, object]:
    matrix = capability_readiness_matrix()
    return {
        **matrix,
        "company_id": str(context.company.id),
        "branch_id": str(context.active_branch.id) if context.active_branch else None,
    }


@router.get("/measurement-foundation", response_model=dict[str, object])
async def economics_measurement_foundation(context: Reader) -> dict[str, object]:
    """Expose policy-neutral source readiness and bounded future-consumer seams."""
    return {
        "contract_version": MEASUREMENT_VERSION,
        "company_id": str(context.company.id),
        "branch_id": str(context.active_branch.id) if context.active_branch else None,
        "source_matrix": operational_measurement_source_matrix(),
        "time_measures": (
            "PAID_TIME",
            "AVAILABLE_TIME",
            "SCHEDULED_TIME",
            "TRAVEL_TIME",
            "ARRIVAL_WAIT_TIME",
            "ACTIVE_JOB_TIME",
            "PAUSED_JOB_TIME",
            "NONPRODUCTIVE_TIME",
            "BREAK_TIME",
            "OVERTIME",
            "UNCLASSIFIED_TIME",
        ),
        "ratio_candidates": (
            "active_job_time_over_paid_time",
            "productive_time_over_available_time",
            "completed_work_time_over_paid_time",
            "scheduled_utilization",
            "capacity_utilization",
        ),
        "canonical_efficiency_kpi": None,
        "beacon_conditions": (
            "MEASUREMENT_INCOMPLETE",
            "PRODUCTIVE_TIME_DECLINING",
            "CONVERSION_CHANGE_OBSERVED",
            "COST_EVIDENCE_STALE",
        ),
        "beacon_thresholds": None,
        "lia_questions": (
            "What do we actually know about productive time?",
            "Why is this efficiency calculation incomplete?",
            "What evidence is missing?",
            "How has conversion changed?",
            "Which cost inputs are authoritative?",
        ),
        "model_lab": {
            "fact_input": "immutable digest-bound measurement snapshot",
            "parameter_input": "separate approved effective-dated policy/model version",
            "output": "separate modeled result with both lineage references",
            "arbitrary_formula_engine": False,
        },
        "mutation_authority": "none",
        "prohibited_outputs": (
            "pricing_change",
            "markup_change",
            "staffing_action",
            "employment_action",
            "accounting_posting",
            "causal_claim",
        ),
    }


@router.get("/workspace", response_model=dict[str, object])
async def economics_workspace(
    session: Session,
    context: Reader,
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
) -> dict[str, object]:
    try:
        return await EconomicsWorkspaceService().overview(
            session, context=context, period_start=start, period_end=end
        )
    except ValueError as error:
        failure = SafeFailure(
            FailureCode.VALIDATION,
            "Business Economics request requires correction.",
            ClientRecovery.USER_CORRECTION_REQUIRED,
            current_correlation_id(),
        )
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, failure.detail()
        ) from error


@router.get("/source-completeness", response_model=dict[str, object])
async def economics_source_completeness(
    session: Session,
    context: Reader,
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
) -> dict[str, object]:
    try:
        workspace = await EconomicsWorkspaceService().overview(
            session, context=context, period_start=start, period_end=end
        )
        return source_completeness_matrix(workspace)
    except ValueError as error:
        failure = SafeFailure(
            FailureCode.VALIDATION,
            "Business Economics source-completeness request requires correction.",
            ClientRecovery.USER_CORRECTION_REQUIRED,
            current_correlation_id(),
        )
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, failure.detail()
        ) from error


@router.get("/cash-operational", response_model=dict[str, object])
async def cash_operational_economics(
    session: Session,
    context: CashOperationalReader,
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
) -> dict[str, object]:
    """Separate earned work, operational obligations, and Accounting cash truth."""
    try:
        return await CashOperationalEconomicsService().overview(
            session, context=context, period_start=start, period_end=end
        )
    except ValueError as error:
        failure = SafeFailure(
            FailureCode.VALIDATION,
            "Cash and operational Economics request requires correction.",
            ClientRecovery.USER_CORRECTION_REQUIRED,
            current_correlation_id(),
        )
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, failure.detail()
        ) from error


@router.get("/operational-sources", response_model=dict[str, object])
async def operational_source_economics(
    session: Session,
    context: OperationalSourceReader,
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
) -> dict[str, object]:
    """Project bounded operational readiness without creating economic truth."""
    try:
        return await OperationalSourceEconomicsService().overview(
            session, context=context, period_start=start, period_end=end
        )
    except ValueError as error:
        failure = SafeFailure(
            FailureCode.VALIDATION,
            "Operational source Economics request requires correction.",
            ClientRecovery.USER_CORRECTION_REQUIRED,
            current_correlation_id(),
        )
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, failure.detail()
        ) from error


@router.get("/administration", response_model=dict[str, object])
async def economics_policy_administration(
    session: Session,
    context: PolicyReader,
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
) -> dict[str, object]:
    try:
        return await EconomicsPolicyAdministrationService().dashboard(
            session,
            context=context,
            period_start=start,
            period_end=end,
        )
    except ValueError as error:
        failure = SafeFailure(
            FailureCode.VALIDATION,
            "Economics policy administration request requires correction.",
            ClientRecovery.USER_CORRECTION_REQUIRED,
            current_correlation_id(),
        )
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, failure.detail()
        ) from error


@router.get("/results/{result_id}", response_model=dict[str, object])
async def economics_result(
    result_id: UUID, session: Session, context: Reader
) -> dict[str, object]:
    try:
        return await EconomicsWorkspaceService().detail(
            session, context=context, result_id=result_id
        )
    except LookupError as error:
        failure = SafeFailure(
            FailureCode.NOT_FOUND,
            "Business Economics result was not found.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        raise HTTPException(status.HTTP_404_NOT_FOUND, failure.detail()) from error


@router.get("/results/{result_id}/lineage", response_model=dict[str, object])
async def economics_result_lineage(
    result_id: UUID, session: Session, context: Reader
) -> dict[str, object]:
    try:
        lineage = await EconomicsResultHistoryService().lineage(
            session, context=context, result_id=result_id
        )
    except EconomicsResultHistoryError as error:
        failure = SafeFailure(
            FailureCode.NOT_FOUND,
            "Business Economics result history was not found.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        raise HTTPException(status.HTTP_404_NOT_FOUND, failure.detail()) from error
    successor_by_predecessor = {
        edge.predecessor_result_id: edge for edge in lineage.supersessions
    }
    predecessor_by_successor = {
        edge.successor_result_id: edge for edge in lineage.supersessions
    }
    return {
        "current_result_id": str(lineage.current.id),
        "results": [
            {
                "result_id": str(item.id),
                "authority_state": "current"
                if item.id == lineage.current.id
                else "historical",
                "result_digest": item.result_digest,
                "package_digest": item.package_digest,
                "computation_digest": item.computation_digest,
                "period_start": item.period_start.isoformat(),
                "period_end": item.period_end.isoformat(),
                "currency": item.currency,
                "predecessor_result_id": str(
                    predecessor_by_successor[item.id].predecessor_result_id
                )
                if item.id in predecessor_by_successor
                else None,
                "successor_result_id": str(
                    successor_by_predecessor[item.id].successor_result_id
                )
                if item.id in successor_by_predecessor
                else None,
                "supersession_reason": successor_by_predecessor[item.id].reason
                if item.id in successor_by_predecessor
                else None,
                "limitations": (item.explanation or {}).get("limitations", []),
            }
            for item in lineage.results
        ],
    }


@router.get("/owner-intelligence", response_model=dict[str, object])
async def owner_intelligence(
    session: Session,
    context: Reader,
    question: Annotated[OwnerQuestion, Query()],
    start: Annotated[date, Query()],
    end: Annotated[date, Query()],
) -> dict[str, object]:
    try:
        return await OwnerIntelligenceService().answer(
            session,
            context=context,
            query=OwnerIntelligenceQuery(question, start, end),
        )
    except ValueError as error:
        failure = SafeFailure(
            FailureCode.VALIDATION,
            "Owner Intelligence request requires correction.",
            ClientRecovery.USER_CORRECTION_REQUIRED,
            current_correlation_id(),
        )
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, failure.detail()
        ) from error

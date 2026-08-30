"""Persistence boundary for admitted deterministic profitability results."""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EconomicsPolicyPermission

from .models import EconomicsProfitabilityResultRecord
from .profitability_admission import AdmittedProfitabilityResult
from .profitability_computation import ProfitabilityComputationRequest


class ProfitabilityPersistenceError(ValueError):
    """Raised when an admitted profitability result cannot become authority."""


class EconomicsProfitabilityPersistenceService:
    def __init__(self, *, audit: AuditService = audit_service) -> None:
        self._audit = audit

    async def persist(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        request: ProfitabilityComputationRequest,
        result: AdmittedProfitabilityResult,
    ) -> EconomicsProfitabilityResultRecord:
        if not context.has_permission(
            EconomicsPolicyPermission.MEASUREMENT_EXECUTE
        ):
            raise ProfitabilityPersistenceError(
                "Economics measurement execution permission denied"
            )
        if request.company_id != context.company.id:
            raise ProfitabilityPersistenceError("cross-Company profitability result")
        identity = f"eco-profitability-result:{result.result_digest}"
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": identity},
        )
        existing = await session.scalar(
            select(EconomicsProfitabilityResultRecord).where(
                EconomicsProfitabilityResultRecord.company_id == context.company.id,
                EconomicsProfitabilityResultRecord.result_identity == identity,
            )
        )
        if existing:
            if existing.result_digest != result.result_digest:
                raise ProfitabilityPersistenceError(
                    "contradictory profitability replay"
                )
            return existing
        analysis = result.computation.computation.analysis
        explanation = result.computation.computation.explanation
        metrics = result.computation.metrics
        components = {
            item.category.value: {
                "state": item.state.value,
                "amount_minor": item.amount_minor,
                "currency": item.currency.upper(),
                "confidence_percent": item.confidence_percent,
                "explanation": item.explanation,
                "evidence": [
                    {
                        "owner": evidence.owner,
                        "source_system": evidence.source_system,
                        "record_type": evidence.record_type,
                        "record_id": evidence.record_id,
                        "source_version": evidence.source_version,
                        "content_digest": evidence.content_digest,
                    }
                    for evidence in item.evidence
                ],
                "allocation_digests": [
                    allocation.input_digest for allocation in item.allocations
                ],
            }
            for item in (
                analysis.revenue,
                analysis.labor,
                analysis.materials,
                analysis.equipment,
                analysis.truck,
                analysis.overhead,
                analysis.gross_profit,
                analysis.net_profit,
            )
        }
        value = EconomicsProfitabilityResultRecord(
            company_id=context.company.id,
            branch_id=request.branch_id,
            subject_id=request.subject_id,
            subject_kind=request.scope.value,
            scope=request.scope.value,
            basis=request.basis.value,
            period_start=request.period.start,
            period_end=request.period.end,
            currency=request.currency,
            admission_id=result.admission_id,
            admission_digest=result.admission_digest,
            package_id=result.package_id,
            package_digest=result.package_digest,
            computation_digest=result.computation.digest,
            result_identity=identity,
            result_digest=result.result_digest,
            metrics={
                "contribution_margin_minor": metrics.contribution_margin_minor,
                "gross_margin_basis_points": metrics.gross_margin_basis_points,
                "net_margin_basis_points": metrics.net_margin_basis_points,
                "allocated_cost_minor": metrics.allocated_cost_minor,
                "fully_burdened_cost_minor": metrics.fully_burdened_cost_minor,
                "confidence_percent": analysis.quality.confidence_percent,
                "completeness_percent": analysis.quality.completeness_percent,
                "freshness_status": analysis.quality.freshness_status,
            },
            components=components,
            quality={
                "confidence_percent": analysis.quality.confidence_percent,
                "completeness_percent": analysis.quality.completeness_percent,
                "freshness_status": analysis.quality.freshness_status,
                "fresh_as_of": analysis.quality.fresh_as_of.isoformat(),
                "explanation": analysis.quality.explanation,
                "missing_categories": [item.value for item in analysis.quality.missing_categories],
            },
            explanation={
                "answer": explanation.answer,
                "findings": [
                    {
                        "kind": item.kind.value,
                        "summary": item.summary,
                        "components": [component.value for component in item.component_categories],
                        "evidence_digests": list(item.evidence_digests),
                        "explanation": item.explanation,
                    }
                    for item in explanation.findings
                ],
                "limitations": list(explanation.limitations),
                "lineage_digest": explanation.lineage_digest,
            },
            acquisition_digests=list(result.computation.acquisition_digests),
            allocation_digests=list(result.computation.allocation_digests),
            explanation_ids=[
                str(item) for item in result.computation.explanation_ids
            ],
            lifecycle="admitted",
            created_by_user_id=context.user.id,
        )
        session.add(value)
        await session.flush()
        details: dict[str, object] = {
            "result_id": str(value.id),
            "result_digest": value.result_digest,
            "subject_id": str(value.subject_id),
            "period_start": value.period_start.isoformat(),
            "period_end": value.period_end.isoformat(),
            "lifecycle": value.lifecycle,
        }
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=EventType.ECONOMICS_PROFITABILITY_ADMITTED,
                entity_type="economics_profitability_result",
                entity_id=value.id,
                company_id=value.company_id,
                user_id=context.user.id,
                payload=details,
            ),
        )
        self._audit.stage(
            session,
            AuditEntry(
                action="economics.profitability.admitted",
                resource_type="economics_profitability_result",
                actor_user_id=context.user.id,
                company_id=value.company_id,
                resource_id=value.id,
                details=details,
            ),
        )
        await session.commit()
        return value

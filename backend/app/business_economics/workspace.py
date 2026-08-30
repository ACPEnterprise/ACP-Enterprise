"""Owner-facing projections over admitted immutable Economics results."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer
from app.jobs.models import Job
from app.platform.branch.models import Branch
from app.platform.permissions.authorization import AuthorizationContext

from .models import CompanyFinancePolicyGap, EconomicsProfitabilityResultRecord


@dataclass(frozen=True, slots=True)
class JobIdentity:
    job_number: str
    status: str
    branch_id: UUID
    branch_name: str
    customer_id: UUID
    customer_name: str
    service_category: str | None


class EconomicsWorkspaceService:
    async def overview(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period_start: date,
        period_end: date,
    ) -> dict[str, object]:
        if period_end < period_start:
            raise ValueError("period end cannot precede period start")
        current = await self._records(session, context, period_start, period_end)
        duration = period_end - period_start
        prior_end = period_start - timedelta(days=1)
        prior_start = prior_end - duration
        prior = await self._records(session, context, prior_start, prior_end)
        job_ids = {
            item.subject_id for item in (*current, *prior) if item.scope == "job"
        }
        identities = await self._job_identities(session, context.company.id, job_ids)
        gaps = (
            await session.scalars(
                select(CompanyFinancePolicyGap).where(
                    CompanyFinancePolicyGap.company_id == context.company.id,
                    CompanyFinancePolicyGap.state.in_(("open", "conflicting")),
                )
            )
        ).all()
        current_projection = self._project(current, identities)
        prior_projection = self._project(prior, identities)
        comparison = self._comparison(current_projection, prior_projection)
        return {
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
            },
            "prior_period": {
                "start": prior_start.isoformat(),
                "end": prior_end.isoformat(),
            },
            **current_projection,
            "comparison": comparison,
            "readiness": {
                "evidence": current_projection["quality_state"],
                "allocation_policy": (
                    "ready"
                    if current_projection["fully_allocated_available"]
                    else "not_configured"
                ),
                "attribution": (
                    "partial"
                    if current_projection["unclassified_job_count"]
                    else "ready"
                ),
                "policy_gaps": [
                    {
                        "gap_key": item.gap_key,
                        "requirement": item.requirement,
                        "state": item.state,
                    }
                    for item in gaps
                ],
            },
            "beacon_conditions": self._conditions(current_projection, comparison),
        }

    async def detail(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        result_id: UUID,
    ) -> dict[str, object]:
        query = select(EconomicsProfitabilityResultRecord).where(
            EconomicsProfitabilityResultRecord.id == result_id,
            EconomicsProfitabilityResultRecord.company_id == context.company.id,
            EconomicsProfitabilityResultRecord.lifecycle == "admitted",
        )
        if context.active_branch is not None:
            query = query.where(
                EconomicsProfitabilityResultRecord.branch_id == context.active_branch.id
            )
        value = await session.scalar(query)
        if value is None:
            raise LookupError("profitability result not found")
        return {
            "id": str(value.id),
            "subject_id": str(value.subject_id),
            "scope": value.scope,
            "period_start": value.period_start.isoformat(),
            "period_end": value.period_end.isoformat(),
            "currency": value.currency,
            "components": value.components,
            "quality": value.quality,
            "explanation": value.explanation,
            "lineage": {
                "result_digest": value.result_digest,
                "admission_digest": value.admission_digest,
                "package_digest": value.package_digest,
                "computation_digest": value.computation_digest,
                "acquisition_digests": value.acquisition_digests,
                "allocation_digests": value.allocation_digests,
                "explanation_ids": value.explanation_ids,
            },
        }

    async def _records(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        start: date,
        end: date,
    ) -> tuple[EconomicsProfitabilityResultRecord, ...]:
        query = select(EconomicsProfitabilityResultRecord).where(
            EconomicsProfitabilityResultRecord.company_id == context.company.id,
            EconomicsProfitabilityResultRecord.period_start == start,
            EconomicsProfitabilityResultRecord.period_end == end,
            EconomicsProfitabilityResultRecord.lifecycle == "admitted",
            EconomicsProfitabilityResultRecord.basis == "actual",
        )
        if context.active_branch is not None:
            query = query.where(
                EconomicsProfitabilityResultRecord.branch_id == context.active_branch.id
            )
        return tuple((await session.scalars(query)).all())

    @staticmethod
    async def _job_identities(
        session: AsyncSession, company_id: UUID, job_ids: set[UUID]
    ) -> dict[UUID, JobIdentity]:
        if not job_ids:
            return {}
        rows = (
            await session.execute(
                select(Job, Customer, Branch)
                .join(Customer, Customer.id == Job.customer_id)
                .join(Branch, Branch.id == Job.branch_id)
                .where(Job.company_id == company_id, Job.id.in_(job_ids))
            )
        ).all()
        return {
            job.id: JobIdentity(
                job.job_number,
                job.status,
                job.branch_id,
                branch.name,
                job.customer_id,
                customer.display_name,
                job.job_type_code,
            )
            for job, customer, branch in rows
        }

    @staticmethod
    def _component(record: EconomicsProfitabilityResultRecord, key: str) -> int | None:
        value: Any = (record.components or {}).get(key)
        if not isinstance(value, dict) or value.get("state") == "missing":
            return None
        amount = value.get("amount_minor")
        return amount if isinstance(amount, int) else None

    @classmethod
    def _project(
        cls,
        records: tuple[EconomicsProfitabilityResultRecord, ...],
        identities: dict[UUID, JobIdentity],
    ) -> dict[str, Any]:
        jobs = [
            item
            for item in records
            if item.scope == "job" and item.subject_id in identities
        ]
        if not jobs:
            return cls._empty_projection("unavailable")
        if len({item.subject_id for item in jobs}) != len(jobs):
            return cls._empty_projection("conflicting")
        currencies = {item.currency.upper() for item in jobs}
        if len(currencies) != 1:
            return cls._empty_projection("conflicting")
        keys = (
            "revenue",
            "labor",
            "materials",
            "equipment",
            "truck",
            "overhead",
            "gross_profit",
            "net_profit",
        )
        directly_computable = [
            item
            for item in jobs
            if all(cls._component(item, key) is not None for key in keys[:5])
        ]
        complete = [
            item
            for item in directly_computable
            if (item.quality or item.metrics).get("completeness_percent") == 100
        ]
        stale = any(
            (item.quality or {}).get("freshness_status") != "current" for item in jobs
        )
        quality_state = (
            "stale"
            if stale
            else ("complete" if len(complete) == len(jobs) else "partial")
        )
        totals = {
            key: sum(cls._component(item, key) or 0 for item in directly_computable)
            for key in keys
        }
        rows = []
        for item in jobs:
            identity = identities[item.subject_id]
            revenue = cls._component(item, "revenue")
            contribution = cls._component(item, "gross_profit")
            rows.append(
                {
                    "result_id": str(item.id),
                    "job_id": str(item.subject_id),
                    "job_number": identity.job_number,
                    "job_status": identity.status,
                    "branch_id": str(identity.branch_id),
                    "branch_name": identity.branch_name,
                    "customer_id": str(identity.customer_id),
                    "customer_name": identity.customer_name,
                    "service_category": identity.service_category,
                    "currency": item.currency,
                    "revenue_minor": revenue,
                    "labor_minor": cls._component(item, "labor"),
                    "materials_minor": cls._component(item, "materials"),
                    "employer_burden_minor": None,
                    "other_direct_cost_minor": sum(
                        (cls._component(item, key) or 0)
                        for key in ("equipment", "truck")
                    ),
                    "contribution_minor": contribution,
                    "net_profit_minor": cls._component(item, "net_profit"),
                    "margin_basis_points": None
                    if not revenue or contribution is None
                    else contribution * 10_000 // revenue,
                    "quality_state": cls._record_quality(item),
                    "confidence_percent": (item.quality or item.metrics).get(
                        "confidence_percent", 0
                    ),
                    "missing_categories": (item.quality or {}).get(
                        "missing_categories", []
                    ),
                }
            )
        rows.sort(
            key=lambda item: (
                item["contribution_minor"] is None,
                -(cast(int | None, item["contribution_minor"]) or 0),
            )
        )
        rollups = {
            dimension: cls._rollup(rows, dimension)
            for dimension in ("service_category", "customer_name", "branch_name")
        }
        fully_allocated = bool(jobs) and all(
            cls._component(item, "overhead") is not None for item in jobs
        )
        return {
            "quality_state": quality_state,
            "currency": currencies.pop(),
            "job_count": len(jobs),
            "complete_job_count": len(complete),
            "unclassified_job_count": sum(
                row["service_category"] is None for row in rows
            ),
            "totals": totals if directly_computable else None,
            "jobs": rows,
            "service_categories": rollups["service_category"],
            "customers": rollups["customer_name"],
            "branches": rollups["branch_name"],
            "fully_allocated_available": fully_allocated,
            "explanation": "Direct contribution totals include only admitted Jobs with complete direct inputs. Missing indirect allocation remains visible and prevents a fully allocated answer.",
        }

    @staticmethod
    def _record_quality(item: EconomicsProfitabilityResultRecord) -> str:
        quality = item.quality or item.metrics
        if quality.get("freshness_status") != "current":
            return "stale"
        return "complete" if quality.get("completeness_percent") == 100 else "partial"

    @staticmethod
    def _rollup(rows: list[dict[str, Any]], dimension: str) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, int]] = defaultdict(
            lambda: {
                "jobs": 0,
                "complete_jobs": 0,
                "revenue_minor": 0,
                "contribution_minor": 0,
            }
        )
        for row in rows:
            name = str(row[dimension] or "Unclassified")
            group = grouped[name]
            group["jobs"] += 1
            if (
                row["contribution_minor"] is not None
                and row["revenue_minor"] is not None
            ):
                group["complete_jobs"] += 1
                group["revenue_minor"] += row["revenue_minor"]
                group["contribution_minor"] += row["contribution_minor"]
        return [
            {
                "label": label,
                **values,
                "quality_state": "complete"
                if values["jobs"] == values["complete_jobs"]
                else "partial",
            }
            for label, values in sorted(grouped.items())
        ]

    @staticmethod
    def _comparison(
        current: dict[str, Any], prior: dict[str, Any]
    ) -> dict[str, object]:
        current_totals, prior_totals = current.get("totals"), prior.get("totals")
        if not current_totals or not prior_totals:
            return {
                "state": "unavailable",
                "reason": "Both comparable periods require complete admitted Job populations.",
            }
        return {
            "state": "available",
            "revenue_change_minor": current_totals["revenue"] - prior_totals["revenue"],
            "contribution_change_minor": current_totals["gross_profit"]
            - prior_totals["gross_profit"],
            "labor_change_minor": current_totals["labor"] - prior_totals["labor"],
            "materials_change_minor": current_totals["materials"]
            - prior_totals["materials"],
            "explanation": "Change is the deterministic difference between equal-length admitted periods.",
        }

    @staticmethod
    def _conditions(
        projection: dict[str, Any], comparison: dict[str, object]
    ) -> list[dict[str, str]]:
        values: list[dict[str, str]] = []
        if projection["quality_state"] != "complete":
            values.append(
                {
                    "kind": "incomplete_economic_evidence",
                    "state": str(projection["quality_state"]),
                }
            )
        if any((row.get("contribution_minor") or 0) < 0 for row in projection["jobs"]):
            values.append({"kind": "negative_profitability", "state": "observed"})
        if (
            comparison.get("state") == "available"
            and cast(int, comparison["contribution_change_minor"]) < 0
        ):
            values.append({"kind": "margin_deterioration", "state": "observed"})
        return values

    @staticmethod
    def _empty_projection(state: str) -> dict[str, Any]:
        return {
            "quality_state": state,
            "currency": None,
            "job_count": 0,
            "complete_job_count": 0,
            "unclassified_job_count": 0,
            "totals": None,
            "jobs": [],
            "service_categories": [],
            "customers": [],
            "branches": [],
            "fully_allocated_available": False,
            "explanation": "No complete admitted Job profitability evidence exists for this period.",
        }

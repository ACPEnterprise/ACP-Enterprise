"""Read-only employer burden evidence from approved Payroll results."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.payroll.models import (
    PayrollGrossCalculationResultRecord,
    PayrollTaxDeductionResultRecord,
)
from app.platform.permissions.authorization import AuthorizationContext

CONTRACT_VERSION: Final = "economics.employer-burden-readiness.v1"
MAX_SOURCE_ROWS: Final = 10_000


class EmployerBurdenReadinessService:
    async def project(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period_start: date,
        period_end: date,
    ) -> dict[str, object]:
        if period_end < period_start:
            raise ValueError("period end cannot precede period start")
        query = (
            select(
                PayrollTaxDeductionResultRecord,
                PayrollGrossCalculationResultRecord,
            )
            .join(
                PayrollGrossCalculationResultRecord,
                (
                    PayrollGrossCalculationResultRecord.company_id
                    == PayrollTaxDeductionResultRecord.company_id
                )
                & (
                    PayrollGrossCalculationResultRecord.id
                    == PayrollTaxDeductionResultRecord.gross_result_id
                ),
            )
            .where(
                PayrollTaxDeductionResultRecord.company_id == context.company.id,
                PayrollTaxDeductionResultRecord.lifecycle == "approved",
                PayrollTaxDeductionResultRecord.review_state == "accepted",
                PayrollGrossCalculationResultRecord.lifecycle == "approved",
                PayrollGrossCalculationResultRecord.review_state == "accepted",
                PayrollGrossCalculationResultRecord.period_start <= period_end,
                PayrollGrossCalculationResultRecord.period_end >= period_start,
            )
            .order_by(
                PayrollGrossCalculationResultRecord.period_start,
                PayrollTaxDeductionResultRecord.employee_id,
            )
            .limit(MAX_SOURCE_ROWS)
        )
        rows = tuple((await session.execute(query)).all())
        return project_employer_burden(
            rows=rows,
            company_id=str(context.company.id),
            period_start=period_start,
            period_end=period_end,
        )


def project_employer_burden(
    *,
    rows: tuple[Any, ...],
    company_id: str,
    period_start: date,
    period_end: date,
) -> dict[str, object]:
    periods: list[dict[str, object]] = []
    family_counts: Counter[str] = Counter()
    currencies: set[str] = set()
    authoritative_total = Decimal(0)
    conflicts = 0
    for tax, gross in rows:
        components = [
            item
            for item in tax.components
            if item.get("kind") == "employer_contribution"
            or item.get("responsibility") == "employer_payroll_tax"
        ]
        component_total = sum(
            (Decimal(str(item["amount"])) for item in components), Decimal(0)
        )
        conflict = component_total != tax.employer_contribution_total
        conflicts += int(conflict)
        if not conflict:
            authoritative_total += tax.employer_contribution_total
        currencies.add(tax.currency.upper())
        projected_components = []
        for item in components:
            key = str(item.get("component_key") or "unclassified")
            family = _family(key)
            family_counts[family] += 1
            projected_components.append(
                {
                    "component_key": key,
                    "family": family,
                    "amount": str(item["amount"]),
                    "currency": tax.currency.upper(),
                    "authority_digest": item.get("authority_digest"),
                    "evidence_digest": item.get("evidence_digest"),
                    "provider_id": item.get("provider_id"),
                    "provider_version": item.get("provider_version"),
                    "jurisdiction_reference": item.get("jurisdiction_reference"),
                }
            )
        periods.append(
            {
                "employee_id": str(tax.employee_id),
                "pay_period_id": str(tax.pay_period_id),
                "period_start": gross.period_start.isoformat(),
                "period_end": gross.period_end.isoformat(),
                "currency": tax.currency.upper(),
                "employer_contribution_total": (
                    str(tax.employer_contribution_total) if not conflict else None
                ),
                "state": "AUTHORITATIVE_READY" if not conflict else "CONFLICTING",
                "components": projected_components,
                "payroll_calculation_digest": tax.calculation_digest,
                "job_attribution_state": "OWNER_POLICY_REQUIRED",
                "job_attribution_requirement": (
                    "approved_employer_burden_to_job_allocation_method"
                ),
            }
        )
    source_state = (
        "CONFLICTING"
        if conflicts or len(currencies) > 1
        else "AUTHORITATIVE_READY"
        if rows
        else "SOURCE_MISSING"
    )
    payload: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "company_id": company_id,
        "scope": "COMPANY",
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "source_state": source_state,
        "approved_employee_period_count": len(rows),
        "conflicting_employee_period_count": conflicts,
        "authoritative_employer_burden_total": (
            str(authoritative_total)
            if rows and not conflicts and len(currencies) == 1
            else None
        ),
        "currency": next(iter(currencies)) if len(currencies) == 1 else None,
        "component_family_counts": dict(sorted(family_counts.items())),
        "employee_periods": periods,
        "readiness": {
            "employer_social_security": _component_state(
                family_counts, "SOCIAL_SECURITY"
            ),
            "employer_medicare": _component_state(family_counts, "MEDICARE"),
            "unemployment": _component_state(family_counts, "UNEMPLOYMENT"),
            "workers_compensation": _component_state(
                family_counts, "WORKERS_COMPENSATION"
            ),
            "employer_benefits": _component_state(family_counts, "EMPLOYER_BENEFIT"),
            "other_approved_burden": _component_state(family_counts, "OTHER"),
        },
        "limitations": (
            "Only approved and accepted Payroll calculation results are projected.",
            "Employee deductions and net pay are not exposed.",
            "Company employer burden is not attributed to a Job without approved policy.",
            "Absence of a component is not an authoritative zero.",
        ),
        "mutation_authority": "none",
    }
    payload["evidence_digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    return payload


def _family(key: str) -> str:
    normalized = key.lower()
    if "social_security" in normalized or "fica_ss" in normalized:
        return "SOCIAL_SECURITY"
    if "medicare" in normalized:
        return "MEDICARE"
    if "unemployment" in normalized or "futa" in normalized or "suta" in normalized:
        return "UNEMPLOYMENT"
    if "workers_comp" in normalized:
        return "WORKERS_COMPENSATION"
    if "benefit" in normalized or "insurance" in normalized:
        return "EMPLOYER_BENEFIT"
    return "OTHER"


def _component_state(counts: Counter[str], family: str) -> str:
    return "AUTHORITATIVE_READY" if counts[family] else "ACCOUNTANT_INPUT_REQUIRED"

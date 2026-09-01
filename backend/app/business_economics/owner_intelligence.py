"""Deterministic owner-question and future-LIA Economics evidence projection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext

from .models import EconomicsProfitabilityResultSupersessionRecord
from .source_completeness import source_completeness_matrix
from .workspace import EconomicsWorkspaceService

CONTRACT_VERSION = "economics.owner-intelligence.v1"
MAX_CONTEXT_ITEMS = 10


class OwnerQuestion(StrEnum):
    LEAST_PROFITABLE_JOBS = "least_profitable_jobs"
    MOST_PROFITABLE_JOBS = "most_profitable_jobs"
    SERVICE_CONTRIBUTION = "service_contribution"
    BRANCH_CONTRIBUTION = "branch_contribution"
    INCOMPLETE_MEASUREMENTS = "incomplete_measurements"
    WHAT_CHANGED = "what_changed"
    MARGIN_LEAKAGE = "margin_leakage"
    LABOR_COST_MOVEMENT = "labor_cost_movement"
    MATERIAL_COST_MOVEMENT = "material_cost_movement"
    FULL_PROFITABILITY_BLOCKERS = "full_profitability_blockers"
    OWNER_DECISIONS_REQUIRED = "owner_decisions_required"
    INSPECT_FIRST = "inspect_first"


@dataclass(frozen=True, slots=True)
class OwnerIntelligenceQuery:
    question: OwnerQuestion
    period_start: date
    period_end: date


class OwnerIntelligenceService:
    async def answer(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        query: OwnerIntelligenceQuery,
    ) -> dict[str, object]:
        projection = await EconomicsWorkspaceService().overview(
            session,
            context=context,
            period_start=query.period_start,
            period_end=query.period_end,
        )
        answer = self._select(query.question, projection)
        source_references = await self._references_with_history(session, answer)
        canonical = {
            "contract_version": CONTRACT_VERSION,
            "company_id": str(context.company.id),
            "branch_id": str(context.active_branch.id)
            if context.active_branch
            else None,
            "period": projection["period"],
            "question": query.question.value,
            "quality_state": projection["quality_state"],
            "currency": projection["currency"],
            "answer": answer,
        }
        digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            **canonical,
            "answer": answer,
            "context_packet": {
                "version": CONTRACT_VERSION,
                "evidence_digest": digest,
                "classification": self._classification(projection),
                "completeness": projection["quality_state"],
                "freshness": self._freshness(projection),
                "limitations": self._limitations(projection),
                "source_references": source_references,
                "result_authority": "immutable_current_results_only",
                "mutation_authority": "none",
            },
        }

    @staticmethod
    def _select(question: OwnerQuestion, value: dict[str, Any]) -> dict[str, object]:
        jobs = list(value["jobs"])
        if question in {
            OwnerQuestion.LEAST_PROFITABLE_JOBS,
            OwnerQuestion.MOST_PROFITABLE_JOBS,
        }:
            measured = [row for row in jobs if row["contribution_minor"] is not None]
            measured.sort(
                key=lambda row: row["contribution_minor"],
                reverse=question is OwnerQuestion.MOST_PROFITABLE_JOBS,
            )
            return {"kind": "jobs", "items": measured[:MAX_CONTEXT_ITEMS]}
        if question is OwnerQuestion.SERVICE_CONTRIBUTION:
            return {
                "kind": "service_categories",
                "items": value["service_categories"][:MAX_CONTEXT_ITEMS],
            }
        if question is OwnerQuestion.BRANCH_CONTRIBUTION:
            return {"kind": "branches", "items": value["branches"][:MAX_CONTEXT_ITEMS]}
        if question is OwnerQuestion.INCOMPLETE_MEASUREMENTS:
            return {
                "kind": "incomplete_jobs",
                "items": [row for row in jobs if row["quality_state"] != "complete"][
                    :MAX_CONTEXT_ITEMS
                ],
                "excluded_job_count": value["excluded_job_count"],
                "unclassified_job_count": value["unclassified_job_count"],
            }
        if question is OwnerQuestion.WHAT_CHANGED:
            return {"kind": "period_comparison", "comparison": value["comparison"]}
        if question in {
            OwnerQuestion.LABOR_COST_MOVEMENT,
            OwnerQuestion.MATERIAL_COST_MOVEMENT,
        }:
            component = (
                "labor"
                if question is OwnerQuestion.LABOR_COST_MOVEMENT
                else "materials"
            )
            comparison = value["comparison"]
            return {
                "kind": "component_movement",
                "component": component,
                "state": comparison.get("state"),
                "change_minor": comparison.get(f"{component}_change_minor"),
                "comparison": comparison,
                "limitation": "Measured co-movement does not establish causality.",
            }
        if question is OwnerQuestion.FULL_PROFITABILITY_BLOCKERS:
            completeness = source_completeness_matrix(value)
            exceptions = cast(list[dict[str, object]], completeness["exceptions"])
            return {
                "kind": "profitability_blockers",
                "items": exceptions[:MAX_CONTEXT_ITEMS],
                "fully_allocated_available": value["fully_allocated_available"],
            }
        if question is OwnerQuestion.OWNER_DECISIONS_REQUIRED:
            readiness = value["readiness"]
            return {
                "kind": "owner_decisions",
                "items": readiness.get("policy_gaps", [])[:MAX_CONTEXT_ITEMS],
                "allocation": readiness.get("allocation_authority"),
                "limitation": "This answer identifies configuration authority; it does not select a policy.",
            }
        if question is OwnerQuestion.INSPECT_FIRST:
            completeness = source_completeness_matrix(value)
            exceptions = cast(list[dict[str, object]], completeness["exceptions"])
            return {
                "kind": "inspection_priority",
                "items": exceptions[:MAX_CONTEXT_ITEMS],
                "ordering": "conflicting, stale, policy required, source required, external gate, partial, unavailable",
            }
        return {
            "kind": "economic_findings",
            "items": value["beacon_conditions"][:MAX_CONTEXT_ITEMS],
            "warning": "Conditions are measured evidence, not causal diagnosis or action authority.",
        }

    @staticmethod
    def _classification(value: dict[str, Any]) -> str:
        return {
            "complete": "KNOWN",
            "partial": "INCOMPLETE",
            "stale": "STALE",
            "conflicting": "CONFLICTING",
            "unavailable": "UNAVAILABLE",
        }.get(value["quality_state"], "UNAVAILABLE")

    @staticmethod
    def _freshness(value: dict[str, Any]) -> str:
        return (
            "STALE"
            if value["quality_state"] == "stale"
            else "CURRENT_OR_EXPLICITLY_INCOMPLETE"
        )

    @staticmethod
    def _limitations(value: dict[str, Any]) -> list[str]:
        limitations: list[str] = []
        if value["quality_state"] != "complete":
            limitations.append("economic_evidence_is_not_complete")
        if not value["fully_allocated_available"]:
            limitations.append("allocated_profitability_unavailable")
        if value["unclassified_job_count"]:
            limitations.append("service_category_attribution_incomplete")
        return limitations

    @staticmethod
    def _references(answer: dict[str, Any]) -> list[dict[str, str]]:
        return [
            {
                "domain": "business-economics",
                "entity_type": "profitability_result",
                "entity_id": str(item["result_id"]),
                "evidence_digest": str(item["result_digest"]),
                "package_digest": str(item["package_digest"]),
                "computation_digest": str(item["computation_digest"]),
                "authority_state": str(item["authority_state"]),
            }
            for item in answer.get("items", [])
            if isinstance(item, dict) and item.get("result_id")
        ][:MAX_CONTEXT_ITEMS]

    @classmethod
    async def _references_with_history(
        cls, session: AsyncSession, answer: dict[str, Any]
    ) -> list[dict[str, str | None]]:
        references: list[dict[str, str | None]] = [
            dict(item) for item in cls._references(answer)
        ]
        ids = [UUID(item["entity_id"]) for item in references]
        if not ids:
            return references
        edges = (
            await session.scalars(
                select(EconomicsProfitabilityResultSupersessionRecord).where(
                    EconomicsProfitabilityResultSupersessionRecord.successor_result_id.in_(
                        ids
                    )
                )
            )
        ).all()
        predecessor_by_successor: dict[str, dict[str, str | None]] = {
            str(edge.successor_result_id): {
                "predecessor_result_id": str(edge.predecessor_result_id),
                "supersession_reason": edge.reason,
                "supersession_digest": edge.supersession_digest,
            }
            for edge in edges
        }
        for reference in references:
            entity_id = reference["entity_id"]
            if entity_id is None:
                continue
            reference.update(
                predecessor_by_successor.get(
                    entity_id,
                    {
                        "predecessor_result_id": None,
                        "supersession_reason": None,
                        "supersession_digest": None,
                    },
                )
            )
        return references

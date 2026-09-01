"""Read-only owner administration projection for Economics authority."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext

from .models import (
    CompanyFinancePolicyGap,
    CompanyFinancePolicyParameter,
    CompanyFinancePolicyVersion,
    FinancePolicySnapshotRecord,
)
from .policy_authority import POLICY_FAMILY_REGISTRY
from .source_completeness import source_completeness_matrix
from .workspace import EconomicsWorkspaceService

ADMINISTRATION_VERSION = "economics.policy-administration.v1"


class EconomicsPolicyAdministrationService:
    async def dashboard(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period_start: date,
        period_end: date,
    ) -> dict[str, object]:
        workspace = await EconomicsWorkspaceService().overview(
            session,
            context=context,
            period_start=period_start,
            period_end=period_end,
        )
        policies = tuple(
            (
                await session.scalars(
                    select(CompanyFinancePolicyVersion)
                    .where(CompanyFinancePolicyVersion.company_id == context.company.id)
                    .order_by(
                        CompanyFinancePolicyVersion.family_key,
                        CompanyFinancePolicyVersion.policy_version.desc(),
                    )
                )
            ).all()
        )
        parameters = tuple(
            (
                await session.scalars(
                    select(CompanyFinancePolicyParameter).where(
                        CompanyFinancePolicyParameter.company_id == context.company.id
                    )
                )
            ).all()
        )
        gaps = tuple(
            (
                await session.scalars(
                    select(CompanyFinancePolicyGap)
                    .where(CompanyFinancePolicyGap.company_id == context.company.id)
                    .order_by(
                        CompanyFinancePolicyGap.family_key,
                        CompanyFinancePolicyGap.effective_start,
                    )
                )
            ).all()
        )
        snapshots = tuple(
            (
                await session.scalars(
                    select(FinancePolicySnapshotRecord)
                    .where(FinancePolicySnapshotRecord.company_id == context.company.id)
                    .order_by(FinancePolicySnapshotRecord.created_at.desc())
                    .limit(20)
                )
            ).all()
        )
        shadowed = {
            item.supersedes_policy_id
            for item in policies
            if item.supersedes_policy_id is not None
        }
        parameter_keys: dict[str, set[str]] = {}
        for item in parameters:
            parameter_keys.setdefault(item.family_key, set()).add(item.parameter_key)
        open_gap_families = {
            item.family_key for item in gaps if item.state in {"open", "conflicting"}
        }
        families = []
        for key, definition in POLICY_FAMILY_REGISTRY.items():
            versions = [item for item in policies if item.family_key == key]
            current = next(
                (
                    item
                    for item in versions
                    if item.id not in shadowed and item.lifecycle == "approved"
                ),
                None,
            )
            configured = bool(current and current.disposition == "selected")
            families.append(
                {
                    "family_key": key,
                    "title": definition.title,
                    "decision_id": definition.finance_decision_id,
                    "state": (
                        "CONFLICTING"
                        if key in open_gap_families
                        and any(
                            item.family_key == key and item.state == "conflicting"
                            for item in gaps
                        )
                        else (
                            "CONFIGURED"
                            if configured
                            else "OWNER_DECISION_REQUIRED"
                            if current is None or current.disposition == "deferred"
                            else "UNCONFIGURED"
                        )
                    ),
                    "current_policy_id": str(current.id) if current else None,
                    "current_version": current.policy_version if current else None,
                    "current_strategy": current.strategy_key if current else None,
                    "supported_strategies": list(definition.supported_strategies),
                    "required_parameter_keys": sorted(definition.parameter_types),
                    "configured_parameter_keys": sorted(parameter_keys.get(key, set())),
                    "effective_start": current.effective_start.isoformat()
                    if current
                    else None,
                    "policy_digest": current.policy_digest if current else None,
                }
            )
        history = [
            {
                "policy_id": str(item.id),
                "family_key": item.family_key,
                "version": item.policy_version,
                "strategy": item.strategy_key,
                "disposition": item.disposition,
                "lifecycle": item.lifecycle,
                "authority_state": "historical"
                if item.id in shadowed or item.lifecycle != "approved"
                else "current",
                "effective_start": item.effective_start.isoformat(),
                "effective_end": item.effective_end.isoformat()
                if item.effective_end
                else None,
                "supersedes_policy_id": str(item.supersedes_policy_id)
                if item.supersedes_policy_id
                else None,
                "definition_version": item.definition_version,
                "decision_evidence_digest": item.decision_evidence_digest,
                "policy_digest": item.policy_digest,
            }
            for item in policies
        ]
        safe_gaps = [
            {
                "family_key": item.family_key,
                "gap_key": item.gap_key,
                "requirement": item.requirement,
                "state": item.state.upper(),
                "authority_dependency": item.authority_dependency,
                "effective_start": item.effective_start.isoformat(),
                "gap_digest": item.gap_digest,
            }
            for item in gaps
        ]
        safe_snapshots = [
            {
                "snapshot_id": str(item.id),
                "subject_identity": item.subject_identity,
                "as_of": item.as_of_date.isoformat(),
                "policy_count": len(item.policy_ids),
                "deferred_family_keys": item.deferred_family_keys,
                "parameter_gap_count": len(item.parameter_gap_digests),
                "definition_version": item.definition_version,
                "snapshot_digest": item.snapshot_digest,
            }
            for item in snapshots
        ]
        canonical: dict[str, Any] = {
            "version": ADMINISTRATION_VERSION,
            "company_id": str(context.company.id),
            "branch_id": str(context.active_branch.id)
            if context.active_branch
            else None,
            "period": workspace["period"],
            "readiness": source_completeness_matrix(workspace),
            "policy_families": families,
            "policy_history": history,
            "policy_gaps": safe_gaps,
            "policy_snapshots": safe_snapshots,
            "mutation_authority": "none",
        }
        fingerprint = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {**canonical, "administration_fingerprint": fingerprint}

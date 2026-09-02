"""Minimum-necessary Asset/Fleet context for governed LIA retrieval."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AssetPermission

from .models import Asset, AssetActionEvidence, AssetEvidence, AssetRelationship
from .service import AssetService

CONTRACT_VERSION = "ASSET.LIA_CONTEXT.v1"
PROTECTED_IDENTIFIERS = frozenset(
    {"serial_reference", "vin", "license_plate", "provider_identity"}
)
MAX_HISTORY = 20


class AssetLiaContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: str = CONTRACT_VERSION
    entity_id: UUID
    company_id: UUID
    branch_id: UUID
    authorization_version: int
    asset_number: str
    display_name: str
    asset_class: str
    lifecycle: str
    version: int
    readiness: str
    readiness_reasons: tuple[str, ...]
    evidence_states: dict[str, int]
    relationship_states: dict[str, int]
    action_states: dict[str, int]
    limitations: tuple[str, ...]
    observed_at: datetime
    evidence_digest: str

    def safe_summary(self) -> str:
        evidence = (
            ", ".join(
                f"{key}={value}" for key, value in sorted(self.evidence_states.items())
            )
            or "none"
        )
        actions = (
            ", ".join(
                f"{key}={value}" for key, value in sorted(self.action_states.items())
            )
            or "none"
        )
        return (
            f"{self.asset_class.replace('_', ' ').title()} {self.display_name} is {self.lifecycle}. "
            f"Readiness: {self.readiness}. Safe evidence: {evidence}. Operational history: {actions}."
        )


class AssetLiaContextService:
    async def project(
        self, session: AsyncSession, *, context: AuthorizationContext, asset_id: UUID
    ) -> AssetLiaContext | None:
        if not context.has_permission(AssetPermission.READ):
            return None
        asset = await session.scalar(
            select(Asset).where(
                Asset.id == asset_id,
                Asset.company_id == context.company.id,
                Asset.branch_id.in_(context.authorized_branch_ids),
            )
        )
        if asset is None:
            return None
        evidence_rows = list(
            (
                await session.scalars(
                    select(AssetEvidence)
                    .where(
                        AssetEvidence.company_id == context.company.id,
                        AssetEvidence.branch_id == asset.branch_id,
                        AssetEvidence.asset_id == asset.id,
                    )
                    .order_by(AssetEvidence.occurred_at.desc(), AssetEvidence.id.desc())
                    .limit(MAX_HISTORY)
                )
            ).all()
        )
        readiness, reasons = AssetService.readiness(asset, evidence_rows)
        safe_evidence = [
            row
            for row in evidence_rows
            if row.evidence_type not in PROTECTED_IDENTIFIERS
        ]
        relationship_states = await _counts(
            session,
            AssetRelationship.relationship_type,
            AssetRelationship.company_id == context.company.id,
            AssetRelationship.branch_id == asset.branch_id,
            AssetRelationship.asset_id == asset.id,
            AssetRelationship.valid_to.is_(None),
        )
        action_states = await _counts(
            session,
            AssetActionEvidence.action_type,
            AssetActionEvidence.company_id == context.company.id,
            AssetActionEvidence.branch_id == asset.branch_id,
            AssetActionEvidence.asset_id == asset.id,
        )
        evidence_states: dict[str, int] = {}
        for row in safe_evidence:
            key = f"{row.evidence_type}:{row.state}"
            evidence_states[key] = evidence_states.get(key, 0) + 1
        limitations = (
            "protected_asset_identifiers_excluded",
            "warranty_evidence_is_not_coverage_adjudication",
            "maintenance_and_inspection_policy_may_be_unconfigured",
            "no_asset_mutation_authority",
        )
        observed_at = datetime.now(timezone.utc)
        canonical = {
            "contract_version": CONTRACT_VERSION,
            "entity_id": str(asset.id),
            "company_id": str(context.company.id),
            "branch_id": str(asset.branch_id),
            "authorization_version": context.authorization_version,
            "asset_number": asset.asset_number,
            "display_name": asset.display_name,
            "asset_class": asset.asset_class,
            "lifecycle": asset.lifecycle,
            "version": asset.version,
            "readiness": readiness,
            "readiness_reasons": reasons,
            "evidence_states": evidence_states,
            "relationship_states": relationship_states,
            "action_states": action_states,
            "limitations": limitations,
        }
        digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return AssetLiaContext(
            entity_id=asset.id,
            company_id=context.company.id,
            branch_id=asset.branch_id,
            authorization_version=context.authorization_version,
            asset_number=asset.asset_number,
            display_name=asset.display_name,
            asset_class=asset.asset_class,
            lifecycle=asset.lifecycle,
            version=asset.version,
            readiness=readiness,
            readiness_reasons=tuple(reasons),
            evidence_states=evidence_states,
            relationship_states=relationship_states,
            action_states=action_states,
            limitations=limitations,
            observed_at=observed_at,
            evidence_digest=digest,
        )


async def _counts(
    session: AsyncSession, column: Any, *predicates: Any
) -> dict[str, int]:
    rows = (
        await session.execute(
            select(column, func.count())
            .where(*predicates)
            .group_by(column)
            .order_by(column)
        )
    ).all()
    return {str(state): int(count) for state, count in rows}


asset_lia_context_service = AssetLiaContextService()

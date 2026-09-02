"""Bounded read-only composition of operational evidence for owner intelligence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, datetime, time, timezone
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.operational_assets.models import Asset, AssetActionEvidence, AssetRelationship
from app.platform.notifications.models import NotificationOutbox
from app.platform.permissions.authorization import AuthorizationContext
from app.workforce.models import (
    WorkforceCapabilityProfile,
    WorkforceCertification,
    WorkforceWorkingAvailability,
)

CONTRACT_VERSION: Final = "economics.operational-source-readiness.v1"
MAX_SOURCE_ROWS: Final = 1000


class OperationalSourceEconomicsService:
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
        start_at = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
        end_at = datetime.combine(period_end, time.max, tzinfo=timezone.utc)
        company_id = context.company.id
        branch_id = context.active_branch.id if context.active_branch else None

        assets_query = select(Asset).where(Asset.company_id == company_id)
        actions_query = (
            select(AssetActionEvidence)
            .where(
                AssetActionEvidence.company_id == company_id,
                AssetActionEvidence.occurred_at >= start_at,
                AssetActionEvidence.occurred_at <= end_at,
            )
            .order_by(
                AssetActionEvidence.occurred_at.desc(), AssetActionEvidence.id.desc()
            )
            .limit(MAX_SOURCE_ROWS)
        )
        relationships_query = (
            select(AssetRelationship)
            .where(
                AssetRelationship.company_id == company_id,
                AssetRelationship.relationship_type.in_(
                    ("customer", "service_location", "job")
                ),
                AssetRelationship.valid_from <= end_at,
                (
                    AssetRelationship.valid_to.is_(None)
                    | (AssetRelationship.valid_to >= start_at)
                ),
            )
            .limit(MAX_SOURCE_ROWS)
        )
        profiles_query = (
            select(WorkforceCapabilityProfile)
            .where(WorkforceCapabilityProfile.company_id == company_id)
            .limit(MAX_SOURCE_ROWS)
        )
        certifications_query = (
            select(WorkforceCertification)
            .where(WorkforceCertification.company_id == company_id)
            .limit(MAX_SOURCE_ROWS)
        )
        availability_query = (
            select(WorkforceWorkingAvailability)
            .where(
                WorkforceWorkingAvailability.company_id == company_id,
                WorkforceWorkingAvailability.end_at >= start_at,
                WorkforceWorkingAvailability.start_at <= end_at,
            )
            .limit(MAX_SOURCE_ROWS)
        )
        communications_query = (
            select(NotificationOutbox)
            .where(
                NotificationOutbox.company_id == company_id,
                NotificationOutbox.notification_type.like("communications.%"),
                NotificationOutbox.created_at >= start_at,
                NotificationOutbox.created_at <= end_at,
            )
            .order_by(
                NotificationOutbox.created_at.desc(), NotificationOutbox.id.desc()
            )
            .limit(MAX_SOURCE_ROWS)
        )
        if branch_id is not None:
            assets_query = assets_query.where(Asset.branch_id == branch_id)
            actions_query = actions_query.where(
                AssetActionEvidence.branch_id == branch_id
            )
            relationships_query = relationships_query.where(
                AssetRelationship.branch_id == branch_id
            )
            availability_query = availability_query.where(
                WorkforceWorkingAvailability.branch_id == branch_id
            )
            communications_query = communications_query.where(
                NotificationOutbox.branch_id == branch_id
            )

        assets = tuple(
            (await session.scalars(assets_query.limit(MAX_SOURCE_ROWS))).all()
        )
        actions = tuple((await session.scalars(actions_query)).all())
        relationships = tuple((await session.scalars(relationships_query)).all())
        profiles = tuple((await session.scalars(profiles_query)).all())
        certifications = tuple((await session.scalars(certifications_query)).all())
        availability = tuple((await session.scalars(availability_query)).all())
        communications = tuple((await session.scalars(communications_query)).all())
        return operational_source_projection(
            period_start=period_start,
            period_end=period_end,
            assets=assets,
            actions=actions,
            relationships=relationships,
            profiles=profiles,
            certifications=certifications,
            availability=availability,
            communications=communications,
        )


def operational_source_projection(
    *,
    period_start: date,
    period_end: date,
    assets: tuple[Asset, ...],
    actions: tuple[AssetActionEvidence, ...],
    relationships: tuple[AssetRelationship, ...],
    profiles: tuple[WorkforceCapabilityProfile, ...],
    certifications: tuple[WorkforceCertification, ...],
    availability: tuple[WorkforceWorkingAvailability, ...],
    communications: tuple[NotificationOutbox, ...],
) -> dict[str, object]:
    asset_by_id = {item.id: item for item in assets}
    action_counts = Counter(item.action_type for item in actions)
    service_counts = Counter(
        item.asset_id for item in actions if item.action_type == "service_link"
    )
    latest_action: dict[tuple[UUID, str], AssetActionEvidence] = {}
    for item in sorted(
        actions, key=lambda row: (row.occurred_at, str(row.id)), reverse=True
    ):
        latest_action.setdefault((item.asset_id, item.action_type), item)
    attention = []
    for (asset_id, action_type), item in latest_action.items():
        if action_type not in {"out_of_service", "inspection", "maintenance"}:
            continue
        if item.state not in {
            "due",
            "fail",
            "attention_required",
            "deferred",
            "out_of_service",
            "insufficient_evidence",
        }:
            continue
        asset = asset_by_id.get(asset_id)
        attention.append(
            {
                "asset_id": str(asset_id),
                "asset_number": asset.asset_number if asset else "Unavailable",
                "asset_class": asset.asset_class if asset else "unknown",
                "condition": action_type,
                "state": item.state,
                "evidence_digest": item.evidence_digest,
            }
        )
    repeated = [
        {
            "asset_id": str(asset_id),
            "asset_number": asset_by_id[asset_id].asset_number,
            "service_evidence_count": count,
        }
        for asset_id, count in sorted(
            service_counts.items(), key=lambda pair: (-pair[1], str(pair[0]))
        )
        if count >= 2 and asset_id in asset_by_id
    ][:25]
    relationship_counts = Counter(item.relationship_type for item in relationships)
    certification_counts = Counter(item.status for item in certifications)
    availability_counts = Counter(item.status for item in availability)
    communication_counts = Counter(item.status for item in communications)
    communication_failures = sum(
        communication_counts[state]
        for state in ("failed", "ambiguous", "canceled", "suppressed")
    )

    sources = [
        _source(
            "customer_equipment",
            "ADMISSIBLE" if assets else "SOURCE_REQUIRED",
            len(assets),
            "Operational Assets owns equipment identity and scoped relationships; no value or depreciation is inferred.",
        ),
        _source(
            "asset_service_history",
            "ADMISSIBLE" if action_counts["service_link"] else "SOURCE_REQUIRED",
            action_counts["service_link"],
            "Typed service-link evidence supports association and history, not causality or cost.",
        ),
        _source(
            "fleet_readiness",
            "ADMISSIBLE"
            if any(item.asset_class == "vehicle" for item in assets)
            else "SOURCE_REQUIRED",
            sum(item.asset_class == "vehicle" for item in assets),
            "Assignment, inspection, maintenance, and out-of-service evidence are operational facts; Fleet cost remains unavailable.",
        ),
        _source(
            "workforce_readiness",
            "PARTIAL" if profiles else "SOURCE_REQUIRED",
            len(profiles),
            "Capability, certification, and availability evidence is admissible; dispatch assignment alone is not economic labor attribution.",
        ),
        _source(
            "communications_delivery",
            "ADMISSIBLE" if communications else "SOURCE_REQUIRED",
            len(communications),
            "Delivery lifecycle is operational evidence and does not prove acceptance, payment, revenue, or conversion.",
        ),
        _source(
            "accounting_readiness",
            "EXTERNAL_GATE",
            0,
            "Only safe Migration/native Accounting readiness metadata may be consumed. Cash totals remain unavailable until admitted Accounting reporting authority exists.",
        ),
        _source(
            "warranty_callback",
            "PARTIAL" if action_counts["warranty_evidence"] else "SOURCE_REQUIRED",
            action_counts["warranty_evidence"],
            "Warranty evidence and service history are available, but eligibility, responsibility, corrective-work identity, and financial consequence remain source-required.",
        ),
        _source(
            "capacity_measurement",
            "PARTIAL" if profiles and availability else "SOURCE_REQUIRED",
            len(availability),
            "Availability and Fleet readiness improve capacity readiness; productive-capacity measurement still requires complete Scheduling, Dispatch, completion, and labor attribution evidence.",
        ),
    ]
    questions = [
        _question(
            "repeated_equipment",
            "Which equipment is associated with repeated service?",
            "ANSWERABLE" if repeated else "SOURCE_REQUIRED",
            len(repeated),
            "Association only; repeated service does not prove a callback, defect, or financial loss.",
        ),
        _question(
            "asset_attention",
            "Which Assets are out of service or need operational attention?",
            "ANSWERABLE" if attention else "NOT_APPLICABLE",
            len(attention),
            "Uses latest typed operational evidence; no lost-revenue amount is inferred.",
        ),
        _question(
            "fleet_capacity",
            "What Fleet evidence may affect capacity?",
            "PARTIALLY_ANSWERABLE",
            len([item for item in attention if item["asset_class"] == "vehicle"]),
            "Operational availability may coincide with capacity constraints; no capacity target or economic impact is inferred.",
        ),
        _question(
            "workforce_incomplete",
            "Which Workforce evidence is incomplete?",
            "PARTIALLY_ANSWERABLE" if profiles else "SOURCE_REQUIRED",
            certification_counts["pending"] + certification_counts["expired"],
            "No compensation or subjective Employee score is exposed.",
        ),
        _question(
            "labor_attribution",
            "Which Jobs lack attributable labor evidence?",
            "SOURCE_REQUIRED",
            None,
            "Dispatch assignment identifies operational responsibility, not accepted Payroll-to-Job economic attribution.",
        ),
        _question(
            "communication_failures",
            "Which customer communications failed?",
            "ANSWERABLE" if communications else "SOURCE_REQUIRED",
            communication_failures,
            "Delivery failure does not establish lost revenue or Customer behavior.",
        ),
        _question(
            "accounting_gate",
            "Which financial answers remain Accounting-gated?",
            "EXTERNAL_GATE",
            None,
            "Cash income, cash expense, and ledger conclusions require admitted native Accounting reporting evidence.",
        ),
        _question(
            "readiness_change",
            "What changed in operational readiness?",
            "SOURCE_REQUIRED",
            None,
            "A deterministic comparison requires an accepted prior-period projection; the current projection does not fabricate one.",
        ),
    ]
    conditions: list[dict[str, object]] = [
        {
            "condition": item["condition"],
            "subject_id": item["asset_id"],
            "state": item["state"],
            "evidence_digest": item["evidence_digest"],
            "beacon_authority": "evaluation_only",
        }
        for item in attention
    ]
    if communication_failures:
        conditions.append(
            {
                "condition": "communication_delivery_failure",
                "count": communication_failures,
                "beacon_authority": "evaluation_only",
            }
        )
    if (
        not profiles
        or certification_counts["pending"]
        or certification_counts["expired"]
    ):
        conditions.append(
            {
                "condition": "workforce_readiness_gap",
                "count": certification_counts["pending"]
                + certification_counts["expired"],
                "beacon_authority": "evaluation_only",
            }
        )
    conditions.append(
        {
            "condition": "accounting_readiness_blocker",
            "state": "external_gate",
            "beacon_authority": "evaluation_only",
        }
    )
    findings = []
    if attention:
        findings.append(
            {
                "finding_type": "operational_asset_readiness",
                "classification": "OBSERVED_FACT",
                "summary": f"{len(attention)} Asset readiness condition(s) require inspection.",
                "explanation": "Typed Asset evidence reports an operational state. No cost, lost revenue, or cause is inferred.",
                "limitations": [
                    "Fleet and Asset economic cost evidence is unavailable."
                ],
                "inspect_path": "/assets",
            }
        )
    if communication_failures:
        findings.append(
            {
                "finding_type": "communication_delivery_readiness",
                "classification": "OBSERVED_FACT",
                "summary": f"{communication_failures} communication delivery item(s) require inspection.",
                "explanation": "Delivery lifecycle evidence reports failure or uncertainty; it does not explain Customer behavior.",
                "limitations": [
                    "No acceptance, payment, revenue, or conversion causality is authorized."
                ],
                "inspect_path": "/communications",
            }
        )
    findings.append(
        {
            "finding_type": "accounting_readiness",
            "classification": "INSUFFICIENT_EVIDENCE",
            "summary": "Cash-basis Accounting answers remain control-gated.",
            "explanation": "Operational Payments, Deposits, AR, and AP are not substituted for admitted Accounting truth.",
            "limitations": ["Safe admitted Accounting reporting evidence is required."],
            "inspect_path": "/financial-reports",
        }
    )

    canonical = {
        "version": CONTRACT_VERSION,
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "sources": sources,
        "asset_equipment": {
            "asset_count": len(assets),
            "relationship_counts": dict(sorted(relationship_counts.items())),
            "action_counts": dict(sorted(action_counts.items())),
            "repeated_service": repeated,
            "attention": sorted(
                attention,
                key=lambda item: (str(item["condition"]), str(item["asset_id"])),
            ),
            "economic_cost_state": "UNAVAILABLE",
        },
        "workforce": {
            "profile_count": len(profiles),
            "certification_states": dict(sorted(certification_counts.items())),
            "availability_states": dict(sorted(availability_counts.items())),
            "labor_attribution": "SOURCE_REQUIRED",
            "employee_scoring": "PROHIBITED",
        },
        "communications": {
            "delivery_states": dict(sorted(communication_counts.items())),
            "failure_count": communication_failures,
            "causality_authority": "none",
        },
        "accounting": {
            "readiness": "EXTERNAL_GATE",
            "cash_truth": "REQUIRES_ADMITTED_ACCOUNTING_REPORTING",
            "operational_ar_ap_are_cash": False,
            "protected_migration_rows_accessed": False,
        },
        "owner_questions": questions,
        "owner_exception_center": [
            {
                "source": item["source"],
                "state": item["state"],
                "explanation": item["explanation"],
                "mutation_authority": "none",
            }
            for item in sources
            if item["state"] != "ADMISSIBLE"
        ],
        "luminary_findings": findings,
        "beacon_condition_evidence": conditions,
        "lia": {
            "mode": "read_only_explanation",
            "allowed_topics": [
                "asset_readiness",
                "fleet_readiness",
                "workforce_readiness",
                "communication_delivery",
                "accounting_limitations",
            ],
            "prohibited_inferences": [
                "asset_value_or_cost",
                "employee_scoring",
                "communication_causality",
                "accounting_policy_selection",
            ],
            "mutation_authority": "none",
        },
        "limitations": [
            "No Asset, Fleet, maintenance, warranty, or depreciation cost is inferred.",
            "No Employee performance or communication causality is inferred.",
            "No protected Migration evidence or Accounting amount is retrieved.",
        ],
        "mutation_authority": "none",
    }
    return {
        **canonical,
        "projection_digest": hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _source(key: str, state: str, count: int, explanation: str) -> dict[str, object]:
    return {
        "source": key,
        "state": state,
        "evidence_count": count,
        "explanation": explanation,
    }


def _question(
    key: str, question: str, state: str, count: int | None, limitation: str
) -> dict[str, object]:
    return {
        "key": key,
        "question": question,
        "state": state,
        "count": count,
        "limitation": limitation,
        "mutation_authority": "none",
    }

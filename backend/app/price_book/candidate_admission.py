"""Replay-safe admission of source-backed Price Book candidates as native drafts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .errors import PriceBookConflict, PriceBookValidation
from .models import (
    PriceBookAuditEntry,
    PriceBookCandidateAdmissionRun,
    PriceBookCandidateBinding,
    PriceBookCategory,
    PriceBookPriceVersion,
    PriceBookServiceItem,
)


def canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def category_code(position: int, name: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "-", name.upper()).strip("-")
    return f"AC-{position:02d}-{slug}"[:80]


@dataclass(frozen=True, slots=True)
class CandidatePlan:
    configuration_version: str
    packet_digest: str
    readiness_digest: str
    source_digest: str
    categories: tuple[dict[str, Any], ...]
    services: tuple[dict[str, Any], ...]
    counts: dict[str, int]


async def candidate_review_page(
    session: AsyncSession,
    *,
    company_id: UUID,
    search: str | None,
    category: str | None,
    admission_status: str | None,
    review_flag: str | None,
    limit: int,
    offset: int,
    costs_visible: bool,
) -> dict[str, object]:
    """Return bounded owner-review projections without promoting evidence to price authority."""
    bindings = list(
        (
            await session.scalars(
                select(PriceBookCandidateBinding)
                .where(
                    PriceBookCandidateBinding.company_id == company_id,
                    PriceBookCandidateBinding.entity_type == "service",
                )
                .order_by(PriceBookCandidateBinding.candidate_identity)
            )
        ).all()
    )
    needle = search.strip().casefold() if search else None
    filtered: list[PriceBookCandidateBinding] = []
    for binding in bindings:
        evidence = binding.candidate_evidence
        category_evidence = cast(dict[str, object], evidence.get("category", {}))
        values = (
            str(evidence.get("service_code", "")),
            str(evidence.get("name", "")),
            str(evidence.get("customer_description", "")),
            str(category_evidence.get("source_name", "")),
        )
        if needle and not any(needle in value.casefold() for value in values):
            continue
        if category and values[3] != category:
            continue
        if admission_status and binding.admission_status != admission_status:
            continue
        if review_flag and review_flag not in binding.review_flags:
            continue
        filtered.append(binding)

    counts = {
        "candidate_services": len(bindings),
        "admitted": sum(row.admission_status == "admitted" for row in bindings),
        "held": sum(row.admission_status == "held" for row in bindings),
        "activation_ready": sum(not row.activation_blockers for row in bindings),
        "material_mapping_required": sum(
            "MATERIAL_MAPPING_REQUIRED" in row.review_flags for row in bindings
        ),
        "tax_review_required": sum(
            "TAX_REVIEW_REQUIRED" in row.review_flags for row in bindings
        ),
        "price_review_required": sum(
            "PRICE_EVIDENCE_REVIEW_REQUIRED" in row.review_flags for row in bindings
        ),
    }
    items = []
    for binding in filtered[offset : offset + limit]:
        evidence = binding.candidate_evidence
        category_evidence = cast(dict[str, object], evidence.get("category", {}))
        material = cast(dict[str, object], evidence.get("material_cost_evidence", {}))
        labor = cast(dict[str, object], evidence.get("labor", {}))
        source = cast(dict[str, object], evidence.get("source", {}))
        items.append(
            {
                "candidate_identity": binding.candidate_identity,
                "native_service_item_id": binding.native_entity_id,
                "service_code": evidence.get("service_code"),
                "name": evidence.get("name"),
                "customer_description": evidence.get("customer_description"),
                "category": category_evidence.get("source_name"),
                "admission_status": binding.admission_status,
                "review_flags": binding.review_flags,
                "activation_blockers": binding.activation_blockers,
                "candidate_prices": evidence.get("price_candidates", {}),
                "price_derivation": evidence.get("price_derivation"),
                "labor_hours": labor.get("hours") if costs_visible else None,
                "material_cost_evidence": material.get("amount")
                if costs_visible
                else None,
                "source_sheet": source.get("sheet"),
                "source_row": source.get("row"),
                "source_digest": binding.source_digest,
                "evidence_digest": binding.evidence_digest,
                "tax_decision_group": evidence.get("tax_decision_group"),
                "conflict_reason": evidence.get("conflict_reason"),
            }
        )
    return {
        "items": items,
        "counts": counts,
        "total": len(filtered),
        "limit": limit,
        "offset": offset,
        "costs_visible": costs_visible,
    }


def classify_packet(
    configuration: dict[str, Any],
    readiness: dict[str, Any],
    *,
    packet_digest: str | None = None,
    readiness_digest: str | None = None,
) -> CandidatePlan:
    categories = tuple(configuration.get("categories", ()))
    services = tuple(configuration.get("service_candidates", ()))
    audits = {
        item["candidate_identity"]: item for item in readiness.get("service_audits", ())
    }
    if len(categories) != 16 or len(services) != 218 or len(audits) != 218:
        raise PriceBookValidation("Candidate packet row accounting is incomplete.")
    registrations = {
        item["source_key"]: item
        for item in configuration.get("source_registrations", ())
    }
    flat_rate = registrations.get("flat_rate_price_book")
    if not flat_rate or not flat_rate.get("sha256"):
        raise PriceBookValidation("Flat-rate source provenance is unavailable.")

    classified: list[dict[str, Any]] = []
    for candidate in services:
        audit = audits.get(candidate["candidate_identity"])
        if audit is None or audit.get("service_code") != candidate.get("service_code"):
            raise PriceBookValidation(
                "Candidate readiness identity does not reconcile."
            )
        conflict = bool(audit["gates"]["SOURCE_CONFLICT"])
        flags = ["OWNER_REVIEW_REQUIRED", "PRICE_EVIDENCE_REVIEW_REQUIRED"]
        blockers = [
            "OWNER_APPROVAL_REQUIRED",
            "PRICE_APPROVAL_REQUIRED",
            "TAX_REVIEW_REQUIRED",
            "EFFECTIVE_DATE_REQUIRED",
        ]
        if candidate["material_cost_evidence"]["amount"] != "0.00":
            flags.append("MATERIAL_MAPPING_REQUIRED")
        flags.append("TAX_REVIEW_REQUIRED")
        if conflict:
            flags.append("SOURCE_CONFLICT")
            blockers.append("SOURCE_CONFLICT")
        classified.append(
            {
                **candidate,
                "admission_status": "held" if conflict else "admitted",
                "review_flags": sorted(set(flags)),
                "activation_blockers": sorted(set(blockers)),
                "conflict_reason": (
                    "WORKBOOK_PRICE_CONFLICTS_WITH_ILLUSTRATIVE_WATER_HEATER_SCRIPT"
                    if conflict
                    else None
                ),
                "tax_decision_group": audit["tax_decision_group"],
            }
        )
    counts = {
        "candidate_categories": len(categories),
        "candidate_services": len(classified),
        "safe_draft_admission": sum(
            item["admission_status"] == "admitted" for item in classified
        ),
        "held_source_conflict": sum(
            item["admission_status"] == "held" for item in classified
        ),
        "material_mapping_required": sum(
            "MATERIAL_MAPPING_REQUIRED" in item["review_flags"] for item in classified
        ),
        "tax_review_required": sum(
            "TAX_REVIEW_REQUIRED" in item["review_flags"] for item in classified
        ),
        "price_review_required": sum(
            "PRICE_EVIDENCE_REVIEW_REQUIRED" in item["review_flags"]
            for item in classified
        ),
        "activation_ready": sum(not item["activation_blockers"] for item in classified),
    }
    if counts != {
        "candidate_categories": 16,
        "candidate_services": 218,
        "safe_draft_admission": 179,
        "held_source_conflict": 39,
        "material_mapping_required": 194,
        "tax_review_required": 218,
        "price_review_required": 218,
        "activation_ready": 0,
    }:
        raise PriceBookValidation(
            "Candidate classifications do not match sealed controls."
        )
    return CandidatePlan(
        configuration_version=str(configuration["candidate_configuration_version"]),
        packet_digest=packet_digest or canonical_digest(configuration),
        readiness_digest=readiness_digest or canonical_digest(readiness),
        source_digest=str(flat_rate["sha256"]),
        categories=categories,
        services=tuple(classified),
        counts=counts,
    )


async def admit_candidate_plan(
    session: AsyncSession,
    *,
    company_id: UUID,
    actor_user_id: UUID,
    plan: CandidatePlan,
    idempotency_key: str,
) -> PriceBookCandidateAdmissionRun:
    """Admit one sealed plan transactionally; exact replay has no side effects."""
    async with session.begin():
        existing = await session.scalar(
            select(PriceBookCandidateAdmissionRun).where(
                PriceBookCandidateAdmissionRun.company_id == company_id,
                PriceBookCandidateAdmissionRun.configuration_version
                == plan.configuration_version,
            )
        )
        if existing is not None:
            if (
                existing.packet_digest != plan.packet_digest
                or existing.readiness_digest != plan.readiness_digest
            ):
                raise PriceBookConflict(
                    "Candidate source changed under an admitted configuration identity."
                )
            return existing

        native_before = {
            "categories": int(
                await session.scalar(
                    select(func.count())
                    .select_from(PriceBookCategory)
                    .where(PriceBookCategory.company_id == company_id)
                )
                or 0
            ),
            "services": int(
                await session.scalar(
                    select(func.count())
                    .select_from(PriceBookServiceItem)
                    .where(PriceBookServiceItem.company_id == company_id)
                )
                or 0
            ),
            "active_versions": int(
                await session.scalar(
                    select(func.count())
                    .select_from(PriceBookPriceVersion)
                    .where(
                        PriceBookPriceVersion.company_id == company_id,
                        PriceBookPriceVersion.status == "active",
                    )
                )
                or 0
            ),
        }
        run = PriceBookCandidateAdmissionRun(
            id=uuid4(),
            company_id=company_id,
            configuration_version=plan.configuration_version,
            packet_digest=plan.packet_digest,
            readiness_digest=plan.readiness_digest,
            idempotency_key=idempotency_key,
            status="completed",
            result_counts={},
            created_by_user_id=actor_user_id,
        )
        session.add(run)
        await session.flush()

        categories_by_name: dict[str, PriceBookCategory] = {}
        created_categories = 0
        for raw in plan.categories:
            position = int(raw["position"])
            name = str(raw["source_name"]).strip()
            code = category_code(position, name)
            category = await session.scalar(
                select(PriceBookCategory).where(
                    PriceBookCategory.company_id == company_id,
                    PriceBookCategory.code == code,
                )
            )
            if category is None:
                category = PriceBookCategory(
                    company_id=company_id,
                    code=code,
                    name=name,
                    description=f"All County source category {position}",
                    status="draft",
                    position=position,
                    created_by_user_id=actor_user_id,
                )
                session.add(category)
                await session.flush()
                created_categories += 1
                _audit(
                    session,
                    company_id=company_id,
                    actor_user_id=actor_user_id,
                    entity_type="price_book_category",
                    entity_id=category.id,
                    action="candidate_admitted",
                    state={"code": code, "review_state": "DRAFT_READY_FOR_REVIEW"},
                )
            elif category.name != name:
                raise PriceBookConflict(
                    "Candidate category identity conflicts with native authority."
                )
            categories_by_name[name] = category
            session.add(
                _binding(
                    run=run,
                    plan=plan,
                    identity=f"category:{position}:{name}",
                    entity_type="category",
                    native_id=category.id,
                    status="admitted",
                    evidence=raw,
                    flags=["OWNER_REVIEW_REQUIRED"],
                    blockers=[],
                )
            )

        created_services = held_services = reused_services = 0
        for candidate in plan.services:
            category = categories_by_name[candidate["category"]["source_name"]]
            native_id: UUID | None = None
            status = str(candidate["admission_status"])
            flags = list(candidate["review_flags"])
            blockers = list(candidate["activation_blockers"])
            if status == "held":
                held_services += 1
            else:
                item = await session.scalar(
                    select(PriceBookServiceItem).where(
                        PriceBookServiceItem.company_id == company_id,
                        PriceBookServiceItem.code == candidate["service_code"],
                    )
                )
                if item is None:
                    item = PriceBookServiceItem(
                        company_id=company_id,
                        branch_id=None,
                        category_id=category.id,
                        code=candidate["service_code"],
                        name=candidate["name"],
                        customer_description=candidate["customer_description"],
                        internal_description=candidate.get("internal_notes"),
                        status="draft",
                        created_by_user_id=actor_user_id,
                    )
                    session.add(item)
                    await session.flush()
                    created_services += 1
                    _audit(
                        session,
                        company_id=company_id,
                        actor_user_id=actor_user_id,
                        entity_type="price_book_service_item",
                        entity_id=item.id,
                        action="candidate_admitted",
                        state={
                            "code": item.code,
                            "status": "draft",
                            "review_flags": flags,
                        },
                    )
                elif (
                    item.category_id != category.id
                    or item.name != candidate["name"]
                    or item.customer_description != candidate["customer_description"]
                ):
                    status = "held"
                    flags.append("IDENTITY_CONFLICT")
                    blockers.append("IDENTITY_CONFLICT")
                    held_services += 1
                else:
                    reused_services += 1
                if status == "admitted":
                    native_id = item.id
            session.add(
                _binding(
                    run=run,
                    plan=plan,
                    identity=candidate["candidate_identity"],
                    entity_type="service",
                    native_id=native_id,
                    status=status,
                    evidence=candidate,
                    flags=sorted(set(flags)),
                    blockers=sorted(set(blockers)),
                )
            )

        result: dict[str, object] = {
            **plan.counts,
            "created_categories": created_categories,
            "created_services": created_services,
            "reused_services": reused_services,
            "held_services": held_services,
            "native_categories_before": native_before["categories"],
            "native_services_before": native_before["services"],
            "native_active_versions_before": native_before["active_versions"],
            "activated_prices": 0,
        }
        run.result_counts = result
        _audit(
            session,
            company_id=company_id,
            actor_user_id=actor_user_id,
            entity_type="price_book_candidate_admission_run",
            entity_id=run.id,
            action="completed",
            state={"packet_digest": plan.packet_digest, **result},
        )
    return run


def _binding(
    *,
    run: PriceBookCandidateAdmissionRun,
    plan: CandidatePlan,
    identity: str,
    entity_type: str,
    native_id: UUID | None,
    status: str,
    evidence: dict[str, Any],
    flags: list[str],
    blockers: list[str],
) -> PriceBookCandidateBinding:
    source = evidence.get("source", {})
    return PriceBookCandidateBinding(
        company_id=run.company_id,
        admission_run_id=run.id,
        candidate_identity=identity,
        entity_type=entity_type,
        native_entity_id=native_id,
        admission_status=status,
        evidence_digest=canonical_digest(evidence),
        source_key=str(source.get("source_key", "flat_rate_price_book")),
        source_digest=plan.source_digest,
        review_flags=flags,
        activation_blockers=blockers,
        candidate_evidence=evidence,
    )


def _audit(
    session: AsyncSession,
    *,
    company_id: UUID,
    actor_user_id: UUID,
    entity_type: str,
    entity_id: UUID,
    action: str,
    state: dict[str, object],
) -> None:
    session.add(
        PriceBookAuditEntry(
            company_id=company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_user_id,
            new_state=state,
            prior_state=None,
            reason="Source-backed All County candidate admission; no activation.",
            version=1,
        )
    )

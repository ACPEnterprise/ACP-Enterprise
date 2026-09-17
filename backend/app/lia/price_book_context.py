"""Exact, read-only Price Book context built from the authoritative catalog read model."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import PriceBookPermission
from app.price_book.service import price_book_service

from .contracts import EvidenceReference

CONTRACT_VERSION = "PRICE_BOOK.LIA_CONTEXT.v1"
MAX_EXACT_MATCHES = 2


@dataclass(frozen=True)
class PriceBookLookup:
    matches: tuple[UUID, ...]
    evidence: EvidenceReference | None = None
    branch_required: bool = False


class PriceBookLiaContextService:
    async def resolve_exact(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        query: str,
    ) -> PriceBookLookup:
        if not context.has_permission(PriceBookPermission.READ):
            return PriceBookLookup(())
        if context.active_branch is None:
            return PriceBookLookup((), branch_required=True)

        normalized = _normalize(query)
        if not normalized:
            return PriceBookLookup(())
        catalog = await price_book_service.catalog(
            session,
            context=context,
            branch_id=context.active_branch.id,
            search=query,
            item_status="active",
            limit=25,
        )
        matches = tuple(
            item
            for item in catalog.service_items
            if normalized in {_normalize(item.name), _normalize(item.code)}
        )[:MAX_EXACT_MATCHES]
        if len(matches) != 1:
            return PriceBookLookup(tuple(item.id for item in matches))

        item = matches[0]
        current = next(
            (
                version
                for version in catalog.versions
                if version.id == item.current_version_id and version.status == "active"
            ),
            None,
        )
        fields = {
            "contract_version": CONTRACT_VERSION,
            "company_id": str(context.company.id),
            "branch_id": str(context.active_branch.id),
            "authorization_version": context.authorization_version,
            "service_item_id": str(item.id),
            "code": item.code,
            "name": item.name,
            "price_version_id": str(current.id) if current is not None else None,
            "unit_price": str(current.unit_price) if current is not None else None,
            "currency": current.currency if current is not None else None,
            "effective_at": current.effective_at.isoformat()
            if current is not None
            else None,
        }
        digest = hashlib.sha256(
            json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        state = "CURRENT_PRICE" if current is not None else "CURRENT_PRICE_UNAVAILABLE"
        summary = (
            f"{item.name} ({item.code}) is {current.currency} {current.unit_price} "
            f"effective {current.effective_at.date().isoformat()}."
            if current is not None
            else f"{item.name} ({item.code}) has no active current price in the catalog."
        )
        return PriceBookLookup(
            (item.id,),
            EvidenceReference(
                domain="price-book",
                label=f"Price Book service {item.name}",
                authority=CONTRACT_VERSION,
                observed_at=datetime.now(timezone.utc),
                freshness="CURRENT_QUERY",
                entity_id=item.id,
                evidence_digest=digest,
                count=1,
                state=f"{state}|{summary}",
                source_contract_version=CONTRACT_VERSION,
                company_id=context.company.id,
                branch_ids=(context.active_branch.id,),
                authorization_version=context.authorization_version,
                limitations=(
                    "customer_price_only_cost_and_margin_excluded",
                    "exact_name_or_code_match_only",
                ),
            ),
        )


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


price_book_lia_context_service = PriceBookLiaContextService()

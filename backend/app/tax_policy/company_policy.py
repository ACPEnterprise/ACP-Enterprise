from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tax_policy.models import CompanyTaxPolicy


async def effective_company_tax_policy(
    session: AsyncSession, *, company_id: UUID, effective_at: datetime
) -> CompanyTaxPolicy | None:
    policies = tuple(
        (
            await session.scalars(
                select(CompanyTaxPolicy)
                .where(
                    CompanyTaxPolicy.company_id == company_id,
                    CompanyTaxPolicy.status == "certified",
                    CompanyTaxPolicy.effective_at <= effective_at,
                    or_(
                        CompanyTaxPolicy.expires_at.is_(None),
                        CompanyTaxPolicy.expires_at > effective_at,
                    ),
                )
                .order_by(
                    CompanyTaxPolicy.effective_at.desc(),
                    CompanyTaxPolicy.version.desc(),
                )
            )
        ).all()
    )
    if len(policies) > 1 and policies[0].effective_at == policies[1].effective_at:
        raise ValueError("Company tax policy resolution is ambiguous.")
    return policies[0] if policies else None


def customer_treatment(
    policy: CompanyTaxPolicy,
    *,
    component_types: set[str],
    service_item_id: UUID | None = None,
) -> str:
    if any(
        value.get("scope") == "ALL_SERVICES"
        or (
            service_item_id is not None
            and value.get("scope") == "SERVICE_ITEM"
            and value.get("service_item_id") == str(service_item_id)
        )
        for value in policy.authorized_exceptions
    ):
        return "REVIEW_REQUIRED"
    treatments = {policy.customer_service_treatment}
    if "material" in component_types:
        treatments.add(policy.customer_material_treatment)
    return treatments.pop() if len(treatments) == 1 else "REVIEW_REQUIRED"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)

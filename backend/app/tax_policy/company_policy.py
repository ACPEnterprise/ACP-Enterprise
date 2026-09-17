from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext
from app.price_book.errors import PriceBookConflict, PriceBookNotFound
from app.price_book.models import PriceBookAuditEntry
from app.tax_policy.models import CompanyTaxPolicy
from app.tax_policy.schemas import CompanyTaxPolicyCreate, CompanyTaxPolicyUpdate


async def effective_company_tax_policy(
    session: AsyncSession, *, company_id: UUID, effective_at: datetime
) -> CompanyTaxPolicy | None:
    policies = tuple(
        (
            await session.scalars(
                select(CompanyTaxPolicy)
                .where(
                    CompanyTaxPolicy.company_id == company_id,
                    CompanyTaxPolicy.status.in_(("certified", "superseded")),
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


async def list_company_tax_policies(
    session: AsyncSession, *, company_id: UUID
) -> list[CompanyTaxPolicy]:
    return list(
        (
            await session.scalars(
                select(CompanyTaxPolicy)
                .where(CompanyTaxPolicy.company_id == company_id)
                .order_by(
                    CompanyTaxPolicy.effective_at.desc(),
                    CompanyTaxPolicy.version.desc(),
                )
            )
        ).all()
    )


async def create_company_tax_policy(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    payload: CompanyTaxPolicyCreate,
) -> CompanyTaxPolicy:
    latest = await session.scalar(
        select(CompanyTaxPolicy)
        .where(
            CompanyTaxPolicy.company_id == context.company.id,
            CompanyTaxPolicy.policy_identity == payload.policy_identity,
        )
        .order_by(CompanyTaxPolicy.version.desc())
        .limit(1)
    )
    policy = CompanyTaxPolicy(
        company_id=context.company.id,
        policy_identity=payload.policy_identity,
        version=(latest.version + 1) if latest else 1,
        status="draft",
        effective_at=payload.effective_at,
        customer_service_treatment=payload.customer_service_treatment,
        customer_material_treatment=payload.customer_material_treatment,
        purchase_material_tax_handling=payload.purchase_material_tax_handling,
        authority_source=payload.authority_source,
        authority_notes=payload.authority_notes,
        authorized_exceptions=payload.authorized_exceptions,
        supersedes_policy_id=latest.id if latest else None,
        created_by_user_id=context.user.id,
    )
    session.add(policy)
    await session.flush()
    _audit(session, context=context, policy=policy, action="draft_created")
    await session.commit()
    await session.refresh(policy)
    return policy


async def update_company_tax_policy(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    policy_id: UUID,
    payload: CompanyTaxPolicyUpdate,
) -> CompanyTaxPolicy:
    policy = await _draft_for_update(session, context.company.id, policy_id)
    if policy.version != payload.expected_version:
        raise PriceBookConflict("Company tax policy draft changed.")
    for field in (
        "policy_identity",
        "effective_at",
        "customer_service_treatment",
        "customer_material_treatment",
        "purchase_material_tax_handling",
        "authority_source",
        "authority_notes",
        "authorized_exceptions",
    ):
        setattr(policy, field, getattr(payload, field))
    policy.version += 1
    _audit(session, context=context, policy=policy, action="draft_updated")
    await session.commit()
    await session.refresh(policy)
    return policy


async def certify_company_tax_policy(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    policy_id: UUID,
    expected_version: int,
    reason: str,
) -> CompanyTaxPolicy:
    policy = await _draft_for_update(session, context.company.id, policy_id)
    if policy.version != expected_version:
        raise PriceBookConflict("Company tax policy draft changed.")
    competing = await session.scalar(
        select(CompanyTaxPolicy).where(
            CompanyTaxPolicy.company_id == context.company.id,
            CompanyTaxPolicy.status.in_(("certified", "superseded")),
            CompanyTaxPolicy.effective_at == policy.effective_at,
            CompanyTaxPolicy.id != policy.id,
        )
    )
    if competing:
        raise PriceBookConflict(
            "Another Company tax policy already has this effective time."
        )
    predecessor = await session.scalar(
        select(CompanyTaxPolicy)
        .where(
            CompanyTaxPolicy.company_id == context.company.id,
            CompanyTaxPolicy.status == "certified",
            CompanyTaxPolicy.effective_at < policy.effective_at,
        )
        .order_by(CompanyTaxPolicy.effective_at.desc())
        .with_for_update()
        .limit(1)
    )
    if predecessor:
        predecessor.status = "superseded"
        predecessor.expires_at = policy.effective_at
        policy.supersedes_policy_id = predecessor.id
    policy.status = "certified"
    policy.certified_by_user_id = context.user.id
    policy.certified_at = now_utc()
    policy.version += 1
    _audit(session, context=context, policy=policy, action="certified", reason=reason)
    await session.commit()
    await session.refresh(policy)
    return policy


async def _draft_for_update(
    session: AsyncSession, company_id: UUID, policy_id: UUID
) -> CompanyTaxPolicy:
    policy = await session.scalar(
        select(CompanyTaxPolicy)
        .where(
            CompanyTaxPolicy.company_id == company_id,
            CompanyTaxPolicy.id == policy_id,
        )
        .with_for_update()
    )
    if policy is None:
        raise PriceBookNotFound("Company tax policy was not found.")
    if policy.status != "draft":
        raise PriceBookConflict("Certified policy history is immutable.")
    return policy


def _audit(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    policy: CompanyTaxPolicy,
    action: str,
    reason: str = "Company tax policy administration.",
) -> None:
    session.add(
        PriceBookAuditEntry(
            company_id=context.company.id,
            entity_type="company_tax_policy",
            entity_id=policy.id,
            action=action,
            actor_user_id=context.user.id,
            new_state={
                "policy_identity": policy.policy_identity,
                "status": policy.status,
                "effective_at": policy.effective_at.isoformat(),
                "customer_service_treatment": policy.customer_service_treatment,
                "customer_material_treatment": policy.customer_material_treatment,
                "purchase_material_tax_handling": policy.purchase_material_tax_handling,
            },
            reason=reason,
            version=policy.version,
        )
    )

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.branch.models import Branch
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.provider_connections.models import ProviderConnectionBinding

from .models import (
    MarketingProviderAccount,
    MarketingProviderAccountBinding,
    MarketingProviderCoverageManifest,
    MarketingProviderReconciliationFinding,
    MarketingProviderSyncRun,
)
from .schemas import (
    GoogleAdsAccountBindingCreate,
    GoogleAdsAccountBindingResponse,
    GoogleAdsAccountBindingSummary,
    GoogleAdsConnectionReadinessResponse,
    ProviderCoverageResponse,
    ProviderSyncStatusResponse,
    ReconciliationFindingResponse,
)


class ProviderBindingError(ValueError):
    pass


class MarketingProviderService:
    async def google_ads_connection_readiness(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> GoogleAdsConnectionReadinessResponse:
        settings = get_settings()
        connection = await session.scalar(
            select(ProviderConnectionBinding)
            .where(
                ProviderConnectionBinding.company_id == context.company.id,
                ProviderConnectionBinding.provider_family == "google_ads",
                ProviderConnectionBinding.environment == settings.environment,
            )
            .order_by(desc(ProviderConnectionBinding.created_at))
            .limit(1)
        )
        prefix = f"marketing/{settings.environment}/google-ads/"
        references = (
            settings.google_ads_oauth_client_reference,
            settings.google_ads_developer_token_reference,
        )
        safe_custody = all(
            reference is not None and reference.startswith(prefix)
            for reference in references
        )
        checks = {
            "oauth_client_not_configured": bool(
                settings.google_ads_oauth_client_reference
            ),
            "callback_not_configured": bool(settings.google_ads_callback_uri),
            "developer_token_not_configured": bool(
                settings.google_ads_developer_token_reference
            ),
            "secret_custody_not_environment_safe": safe_custody,
            "live_ingestion_disabled": settings.google_ads_live_access_enabled,
        }
        configuration_blockers = tuple(
            name for name, ready in checks.items() if not ready
        )
        blockers = configuration_blockers + ("owner_oauth_runtime_not_released",)
        bound_count = await session.scalar(
            select(func.count(MarketingProviderAccountBinding.id)).where(
                MarketingProviderAccountBinding.company_id == context.company.id,
                MarketingProviderAccountBinding.branch_id.in_(
                    context.authorized_branch_ids
                ),
            )
        )
        if connection is None:
            any_configuration = any(
                (
                    settings.google_ads_oauth_client_reference,
                    settings.google_ads_developer_token_reference,
                    settings.google_ads_callback_uri,
                    settings.google_ads_live_access_enabled,
                )
            )
            connection_status = (
                "not_configured"
                if not any_configuration
                else "configuration_required"
                if configuration_blockers
                else "ready_to_connect"
            )
        elif connection.state == "active":
            connection_status = "connected"
        elif connection.state in {"revoked", "disabled"}:
            connection_status = "revoked_or_error"
        else:
            connection_status = (
                "ready_to_connect"
                if not configuration_blockers
                else "configuration_required"
            )
        return GoogleAdsConnectionReadinessResponse(
            connection_status=connection_status,
            environment=settings.environment,
            oauth_client_configured=settings.google_ads_oauth_client_reference
            is not None,
            callback_configured=settings.google_ads_callback_uri is not None,
            developer_token_configured=settings.google_ads_developer_token_reference
            is not None,
            environment_safe_secret_custody=safe_custody,
            live_ingestion_enabled=settings.google_ads_live_access_enabled,
            authorization_available=False,
            granted_scopes=tuple(connection.granted_scopes) if connection else (),
            connected_at=connection.consented_at if connection else None,
            bound_account_count=bound_count or 0,
            blockers=blockers,
        )

    async def google_ads_account_bindings(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> tuple[GoogleAdsAccountBindingSummary, ...]:
        rows = (
            await session.execute(
                select(MarketingProviderAccountBinding, MarketingProviderAccount)
                .join(
                    MarketingProviderAccount,
                    MarketingProviderAccount.id
                    == MarketingProviderAccountBinding.provider_account_id,
                )
                .where(
                    MarketingProviderAccountBinding.company_id == context.company.id,
                    MarketingProviderAccountBinding.branch_id.in_(
                        context.authorized_branch_ids
                    ),
                    MarketingProviderAccount.provider_family == "google_ads",
                )
                .order_by(desc(MarketingProviderAccountBinding.bound_at))
            )
        ).all()
        return tuple(
            GoogleAdsAccountBindingSummary(
                id=binding.id,
                branch_id=binding.branch_id,
                provider_account_id=account.id,
                external_customer_id=account.external_account_id,
                descriptive_name=account.display_name,
                currency_code=account.currency,
                time_zone=account.timezone,
                ingestion_enabled=binding.ingestion_enabled,
                bound_at=binding.bound_at,
            )
            for binding, account in rows
        )

    async def bind_google_ads_account(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: GoogleAdsAccountBindingCreate,
    ) -> GoogleAdsAccountBindingResponse:
        if not context.can_access_branch(data.branch_id):
            raise ProviderBindingError("branch_not_authorized")
        branch = await session.scalar(
            select(Branch).where(
                Branch.company_id == context.company.id, Branch.id == data.branch_id
            )
        )
        connection = await session.scalar(
            select(ProviderConnectionBinding).where(
                ProviderConnectionBinding.company_id == context.company.id,
                ProviderConnectionBinding.id == data.connection_binding_id,
                ProviderConnectionBinding.provider_family == "google_ads",
                ProviderConnectionBinding.state == "active",
            )
        )
        if branch is None or connection is None:
            raise ProviderBindingError("provider_binding_scope_invalid")
        account = await session.scalar(
            select(MarketingProviderAccount).where(
                MarketingProviderAccount.company_id == context.company.id,
                MarketingProviderAccount.provider_family == "google_ads",
                MarketingProviderAccount.external_account_id
                == data.external_customer_id,
            )
        )
        if account is None:
            account = MarketingProviderAccount(
                company_id=context.company.id,
                provider_family="google_ads",
                external_account_id=data.external_customer_id,
                display_name=data.descriptive_name,
                state="configured",
                timezone=data.time_zone,
                currency=data.currency_code,
            )
            session.add(account)
            await session.flush()
        existing = await session.scalar(
            select(MarketingProviderAccountBinding).where(
                MarketingProviderAccountBinding.company_id == context.company.id,
                MarketingProviderAccountBinding.provider_account_id == account.id,
                MarketingProviderAccountBinding.branch_id == branch.id,
            )
        )
        if existing is not None:
            raise ProviderBindingError("provider_account_already_bound")
        binding = MarketingProviderAccountBinding(
            company_id=context.company.id,
            branch_id=branch.id,
            provider_account_id=account.id,
            connection_binding_id=connection.id,
            bound_by_user_id=context.user.id,
            ingestion_enabled=data.ingestion_enabled,
        )
        session.add(binding)
        await session.flush()
        details: dict[str, object] = {
            "provider_family": "google_ads",
            "provider_account_id": str(account.id),
            "branch_id": str(branch.id),
            "ingestion_enabled": data.ingestion_enabled,
        }
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=EventType.MARKETING_PROVIDER_ACCOUNT_BOUND,
                entity_type="marketing_provider_account_binding",
                entity_id=binding.id,
                company_id=context.company.id,
                branch_id=branch.id,
                user_id=context.user.id,
                payload={"version": "1.0", **details},
            ),
        )
        audit_service.stage(
            session,
            AuditEntry(
                action="marketing.google_ads.account.bind",
                resource_type="marketing_provider_account_binding",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                branch_id=branch.id,
                resource_id=binding.id,
                reason_code="owner_account_binding",
                details=details,
            ),
        )
        await session.commit()
        await session.refresh(binding)
        return GoogleAdsAccountBindingResponse.model_validate(binding)

    async def sync_status(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> tuple[ProviderSyncStatusResponse, ...]:
        runs = list(
            await session.scalars(
                select(MarketingProviderSyncRun)
                .join(MarketingProviderAccount)
                .join(
                    MarketingProviderAccountBinding,
                    MarketingProviderAccountBinding.provider_account_id
                    == MarketingProviderSyncRun.provider_account_id,
                )
                .where(
                    MarketingProviderSyncRun.company_id == context.company.id,
                    MarketingProviderAccount.provider_family == "google_ads",
                    MarketingProviderAccountBinding.branch_id.in_(
                        context.authorized_branch_ids
                    ),
                )
                .distinct()
                .order_by(desc(MarketingProviderSyncRun.started_at))
                .limit(200)
            )
        )
        return tuple(ProviderSyncStatusResponse.model_validate(item) for item in runs)

    async def coverage(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> tuple[ProviderCoverageResponse, ...]:
        rows = list(
            await session.scalars(
                select(MarketingProviderCoverageManifest)
                .where(
                    MarketingProviderCoverageManifest.company_id == context.company.id,
                    MarketingProviderCoverageManifest.branch_id.in_(
                        context.authorized_branch_ids
                    ),
                )
                .order_by(desc(MarketingProviderCoverageManifest.as_of))
                .limit(200)
            )
        )
        return tuple(ProviderCoverageResponse.model_validate(item) for item in rows)

    async def reconciliation(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> tuple[ReconciliationFindingResponse, ...]:
        rows = list(
            await session.scalars(
                select(MarketingProviderReconciliationFinding)
                .where(
                    MarketingProviderReconciliationFinding.company_id
                    == context.company.id,
                    MarketingProviderReconciliationFinding.branch_id.in_(
                        context.authorized_branch_ids
                    ),
                    MarketingProviderReconciliationFinding.state.in_(
                        ("open", "not_available")
                    ),
                )
                .order_by(desc(MarketingProviderReconciliationFinding.observed_at))
                .limit(200)
            )
        )
        return tuple(
            ReconciliationFindingResponse.model_validate(item) for item in rows
        )


marketing_provider_service = MarketingProviderService()

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.branch.models import Branch
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.provider_connections.models import ProviderConnectionBinding
from app.platform.secrets import SecretProviderError

from .models import (
    MarketingPerformanceObservation,
    MarketingProviderAccount,
    MarketingProviderAccountBinding,
    MarketingProviderCoverageManifest,
    MarketingProviderReconciliationFinding,
    MarketingProviderSyncRun,
    MarketingSearchTermObservation,
)
from .oauth import GoogleAdsOAuthError, build_google_ads_oauth_runtime
from .schemas import (
    GoogleAdsAccountBindingCreate,
    GoogleAdsAccountBindingResponse,
    GoogleAdsAccountBindingSummary,
    GoogleAdsConnectionReadinessResponse,
    MarketingBranchMappingReadiness,
    MarketingEvidencePeriod,
    MarketingReadinessProjection,
    ProviderCoverageResponse,
    ProviderSyncStatusResponse,
    ReconciliationFindingResponse,
)


class ProviderBindingError(ValueError):
    pass


def marketing_spend_availability(
    *,
    spend_count: int,
    performance_count: int,
    evidence_as_of: datetime | None,
    evaluated_at: datetime,
) -> str:
    if spend_count == 0:
        return "UNAVAILABLE"
    if evidence_as_of and evidence_as_of < evaluated_at - timedelta(hours=72):
        return "STALE"
    if spend_count < performance_count:
        return "PARTIAL"
    return "AVAILABLE"


def owner_readiness_state(
    *,
    configuration_blocked: bool,
    connected: bool,
    account_bound: bool,
    ingestion_enabled: bool,
    last_successful_sync_at: datetime | None,
    provider_error: bool,
    unresolved_findings: int,
) -> str:
    if configuration_blocked:
        return "CONFIGURATION_REQUIRED"
    if not connected:
        return "READY_TO_AUTHORIZE"
    if not account_bound:
        return "AUTHORIZED_ACCOUNT_SELECTION_REQUIRED"
    if provider_error or unresolved_findings:
        return "DEGRADED"
    if not ingestion_enabled or last_successful_sync_at is None:
        return "CONNECTED_NOT_INGESTING"
    return "INGESTING"


class MarketingProviderService:
    async def readiness_projection(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        evaluated_at: datetime | None = None,
    ) -> MarketingReadinessProjection:
        now = evaluated_at or datetime.now(timezone.utc)
        runtime = await self.google_ads_connection_readiness(session, context=context)
        mappings = await self.google_ads_account_bindings(session, context=context)
        account_ids = tuple(mapping.provider_account_id for mapping in mappings)
        enabled = any(mapping.ingestion_enabled for mapping in mappings)
        latest_run = None
        last_successful_sync_at = None
        if account_ids:
            latest_run = await session.scalar(
                select(MarketingProviderSyncRun)
                .where(
                    MarketingProviderSyncRun.company_id == context.company.id,
                    MarketingProviderSyncRun.provider_account_id.in_(account_ids),
                )
                .order_by(desc(MarketingProviderSyncRun.started_at))
                .limit(1)
            )
            last_successful_sync_at = await session.scalar(
                select(func.max(MarketingProviderSyncRun.completed_at)).where(
                    MarketingProviderSyncRun.company_id == context.company.id,
                    MarketingProviderSyncRun.provider_account_id.in_(account_ids),
                    MarketingProviderSyncRun.status.in_(
                        ("completed", "completed_with_exceptions")
                    ),
                )
            )
        evidence = None
        performance_count = spend_count = search_count = 0
        if account_ids:
            interval = (
                await session.execute(
                    select(
                        func.min(MarketingPerformanceObservation.interval_start),
                        func.max(MarketingPerformanceObservation.interval_end),
                        func.max(MarketingPerformanceObservation.provider_as_of),
                        func.count(MarketingPerformanceObservation.id),
                        func.sum(
                            case(
                                (
                                    MarketingPerformanceObservation.cost_micros.is_not(
                                        None
                                    ),
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                    ).where(
                        MarketingPerformanceObservation.company_id
                        == context.company.id,
                        MarketingPerformanceObservation.provider_account_id.in_(
                            account_ids
                        ),
                        or_(
                            MarketingPerformanceObservation.branch_id.is_(None),
                            MarketingPerformanceObservation.branch_id.in_(
                                context.authorized_branch_ids
                            ),
                        ),
                    )
                )
            ).one()
            interval_start, interval_end, provider_as_of = interval[:3]
            performance_count, spend_count = (
                int(interval[3] or 0),
                int(interval[4] or 0),
            )
            if interval_start and interval_end and provider_as_of:
                evidence = MarketingEvidencePeriod(
                    interval_start=interval_start,
                    interval_end=interval_end,
                    as_of=provider_as_of,
                )
            if evidence is None:
                coverage_interval = (
                    await session.execute(
                        select(
                            func.min(MarketingProviderCoverageManifest.interval_start),
                            func.max(MarketingProviderCoverageManifest.interval_end),
                            func.max(MarketingProviderCoverageManifest.as_of),
                        ).where(
                            MarketingProviderCoverageManifest.company_id
                            == context.company.id,
                            MarketingProviderCoverageManifest.provider_account_id.in_(
                                account_ids
                            ),
                            or_(
                                MarketingProviderCoverageManifest.branch_id.is_(None),
                                MarketingProviderCoverageManifest.branch_id.in_(
                                    context.authorized_branch_ids
                                ),
                            ),
                        )
                    )
                ).one()
                coverage_start, coverage_end, coverage_as_of = coverage_interval
                if coverage_start and coverage_end and coverage_as_of:
                    evidence = MarketingEvidencePeriod(
                        interval_start=coverage_start,
                        interval_end=coverage_end,
                        as_of=coverage_as_of,
                    )
            search_count = int(
                await session.scalar(
                    select(func.count(MarketingSearchTermObservation.id)).where(
                        MarketingSearchTermObservation.company_id == context.company.id,
                        MarketingSearchTermObservation.provider_account_id.in_(
                            account_ids
                        ),
                        or_(
                            MarketingSearchTermObservation.branch_id.is_(None),
                            MarketingSearchTermObservation.branch_id.in_(
                                context.authorized_branch_ids
                            ),
                        ),
                    )
                )
                or 0
            )
        unresolved = int(
            await session.scalar(
                select(func.count(MarketingProviderReconciliationFinding.id)).where(
                    MarketingProviderReconciliationFinding.company_id
                    == context.company.id,
                    or_(
                        MarketingProviderReconciliationFinding.branch_id.is_(None),
                        MarketingProviderReconciliationFinding.branch_id.in_(
                            context.authorized_branch_ids
                        ),
                    ),
                    MarketingProviderReconciliationFinding.state.in_(
                        ("open", "not_available")
                    ),
                )
            )
            or 0
        )
        provider_error = runtime.connection_status == "revoked_or_error" or (
            latest_run is not None and latest_run.status == "failed"
        )
        spend_availability = marketing_spend_availability(
            spend_count=spend_count,
            performance_count=performance_count,
            evidence_as_of=evidence.as_of if evidence else None,
            evaluated_at=now,
        )
        connected = runtime.connection_status == "connected"
        configuration_blocked = bool(
            set(runtime.blockers) - {"live_ingestion_disabled"}
        ) or (not connected and "live_ingestion_disabled" in runtime.blockers)
        owner_state = owner_readiness_state(
            configuration_blocked=configuration_blocked,
            connected=connected,
            account_bound=bool(mappings),
            ingestion_enabled=enabled,
            last_successful_sync_at=last_successful_sync_at,
            provider_error=provider_error,
            unresolved_findings=unresolved,
        )
        guidance = {
            "CONFIGURATION_REQUIRED": (
                "Ask a platform administrator to complete the named Google Ads runtime configuration checks.",
                "Return here and refresh readiness; do not enter credentials in Marketing.",
            ),
            "READY_TO_AUTHORIZE": (
                "Select Connect Google Ads and complete Google authorization as the owner.",
                "Authorization discovers access only; it does not bind or ingest every visible account.",
            ),
            "AUTHORIZED_ACCOUNT_SELECTION_REQUIRED": (
                "Review the exact accessible Google Ads accounts.",
                "Select the All County account, map its Branch, and explicitly confirm read-only ingestion.",
            ),
            "CONNECTED_NOT_INGESTING": (
                "Enable ingestion for the owner-selected account and choose a bounded history period.",
                "Start the read-only sync, then review reconciliation and evidence coverage.",
            ),
            "INGESTING": (
                "Review the current evidence period, coverage, and reconciliation findings.",
            ),
            "DEGRADED": (
                "Review provider availability, the latest sync, and unresolved reconciliation findings.",
                "Resolve the named evidence gap before relying on Marketing spend.",
            ),
        }[owner_state]
        missing = list(runtime.blockers)
        if not mappings:
            missing.append("owner_selected_account_binding")
        if not enabled:
            missing.append("ingestion_activation")
        if spend_availability in {"UNAVAILABLE", "PARTIAL", "STALE"}:
            missing.append(f"spend_evidence_{spend_availability.lower()}")
        if unresolved:
            missing.append("unresolved_reconciliation_findings")
        return MarketingReadinessProjection(
            company_id=context.company.id,
            as_of=now,
            owner_state=owner_state,
            owner_guidance=guidance,
            provider_configured=all(
                (
                    runtime.oauth_client_configured,
                    runtime.callback_configured,
                    runtime.developer_token_configured,
                )
            ),
            oauth_runtime_ready=all(
                (
                    runtime.oauth_client_configured,
                    runtime.callback_configured,
                    runtime.developer_token_configured,
                    runtime.environment_safe_secret_custody,
                )
            ),
            secret_custody_ready=runtime.environment_safe_secret_custody,
            connection_state=runtime.connection_status,
            account_discovery_state=(
                "COMPLETED_BY_BINDING_EVIDENCE"
                if mappings
                else "REQUIRED"
                if runtime.connection_status == "connected"
                else "NOT_AVAILABLE"
            ),
            account_bound=bool(mappings),
            branch_mappings=tuple(
                MarketingBranchMappingReadiness(
                    branch_id=mapping.branch_id,
                    provider_account_id=mapping.provider_account_id,
                    ingestion_enabled=mapping.ingestion_enabled,
                )
                for mapping in mappings
            ),
            ingestion_enabled=enabled,
            last_successful_sync_at=last_successful_sync_at,
            current_evidence_period=evidence,
            spend_evidence_availability=spend_availability,
            spend_evidence_available=spend_count > 0,
            campaign_evidence_available=performance_count > 0,
            search_term_evidence_available=search_count > 0,
            unresolved_reconciliation_findings=unresolved,
            provider_unavailable=runtime.connection_status
            in {
                "not_configured",
                "configuration_required",
                "revoked_or_error",
            },
            provider_error=provider_error,
            missing_components=tuple(dict.fromkeys(missing)),
        )

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
        references_safe = all(
            reference is not None and reference.startswith(prefix)
            for reference in references
        )
        try:
            runtime = build_google_ads_oauth_runtime(settings)
            safe_custody = references_safe and runtime.ready()
        except (GoogleAdsOAuthError, SecretProviderError, OSError, ValueError):
            safe_custody = False
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
        blockers = configuration_blockers
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
            authorization_available=not configuration_blockers,
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

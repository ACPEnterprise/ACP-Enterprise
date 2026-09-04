"""Ownership proof and fail-closed release for the sanctioned Preview fixture."""

import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.events.models import BusinessEvent
from app.platform.idempotency.models import MutationReceipt
from app.platform.onboarding.models import PreviewFixtureResource
from app.platform.onboarding.service import OnboardingConflictError
from app.platform.permissions.authorization import AuthorizationContext

FIXTURE_KEY = "acp-employee-beta-v1"
AUDIT_RETAINED_TYPES = frozenset({"timekeeping", "field_evidence"})


@dataclass(frozen=True)
class FixtureResourceEvidence:
    resource_key: str
    resource_type: str
    resource_id: UUID
    authority_type: str
    authority_id: UUID
    authority_digest: str


@dataclass(frozen=True)
class FixtureReleaseStep:
    resource_key: str
    release: Callable[[], Awaitable[None]] | None = None


class PreviewFixtureManifestService:
    def __init__(self, configuration: Settings = settings) -> None:
        self.configuration = configuration

    def _authorize(self, fixture_key: str, authorized: bool) -> None:
        if self.configuration.environment != "preview" or not authorized:
            raise OnboardingConflictError(
                "Fixture ownership mutation requires explicit Preview authorization."
            )
        if fixture_key != FIXTURE_KEY:
            raise OnboardingConflictError("Fixture ownership authority does not match.")

    async def register(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        fixture_key: str,
        authorized: bool,
        evidence: FixtureResourceEvidence,
    ) -> PreviewFixtureResource:
        self._authorize(fixture_key, authorized)
        if not evidence.resource_key.startswith("synthetic-beta-"):
            raise OnboardingConflictError("Fixture resource key is not synthetic.")
        if len(evidence.authority_digest) != 64:
            raise OnboardingConflictError("Fixture creation authority digest is invalid.")
        await self._verify_creation_authority(
            session, context=context, evidence=evidence
        )
        async with session.begin():
            existing = await session.scalar(
                select(PreviewFixtureResource)
                .where(
                    PreviewFixtureResource.company_id == context.company.id,
                    PreviewFixtureResource.fixture_key == fixture_key,
                    PreviewFixtureResource.resource_key == evidence.resource_key,
                )
                .with_for_update()
            )
            facts = (
                evidence.resource_type,
                evidence.resource_id,
                evidence.authority_type,
                evidence.authority_id,
                evidence.authority_digest,
            )
            if existing is not None:
                current = (
                    existing.resource_type,
                    existing.resource_id,
                    existing.authority_type,
                    existing.authority_id,
                    existing.authority_digest,
                )
                if current != facts:
                    raise OnboardingConflictError(
                        "Fixture resource key is bound to different authority."
                    )
                return existing
            record = PreviewFixtureResource(
                company_id=context.company.id,
                fixture_key=fixture_key,
                resource_key=evidence.resource_key,
                resource_type=evidence.resource_type,
                resource_id=evidence.resource_id,
                authority_type=evidence.authority_type,
                authority_id=evidence.authority_id,
                authority_digest=evidence.authority_digest,
                created_by_user_id=context.user.id,
            )
            session.add(record)
            await session.flush()
            return record

    @staticmethod
    async def _verify_creation_authority(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        evidence: FixtureResourceEvidence,
    ) -> None:
        if evidence.authority_type == "mutation_receipt":
            authority = await session.scalar(
                select(MutationReceipt).where(
                    MutationReceipt.id == evidence.authority_id,
                    MutationReceipt.company_id == context.company.id,
                    MutationReceipt.state == "completed",
                    MutationReceipt.result_id == evidence.resource_id,
                )
            )
            digest = authority.request_digest if authority is not None else None
        elif evidence.authority_type == "business_event":
            authority = await session.scalar(
                select(BusinessEvent).where(
                    BusinessEvent.id == evidence.authority_id,
                    BusinessEvent.company_id == context.company.id,
                    BusinessEvent.entity_id == evidence.resource_id,
                )
            )
            digest = (
                hashlib.sha256(
                    json.dumps(
                        {
                            "event_type": authority.event_type,
                            "entity_type": authority.entity_type,
                            "entity_id": str(authority.entity_id),
                            "company_id": str(authority.company_id),
                            "branch_id": str(authority.branch_id),
                            "payload": authority.payload,
                            "correlation_id": str(authority.correlation_id),
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                if authority is not None
                else None
            )
        else:
            raise OnboardingConflictError(
                "Fixture creation authority type is unsupported."
            )
        if digest != evidence.authority_digest:
            raise OnboardingConflictError(
                "Fixture creation authority does not match the resource."
            )

    async def release(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        fixture_key: str,
        authorized: bool,
        steps: Sequence[FixtureReleaseStep],
    ) -> tuple[PreviewFixtureResource, ...]:
        self._authorize(fixture_key, authorized)
        keys = tuple(step.resource_key for step in steps)
        if not keys or len(set(keys)) != len(keys):
            raise OnboardingConflictError("Fixture release plan is empty or duplicated.")
        records = tuple(
            (
                await session.scalars(
                    select(PreviewFixtureResource).where(
                        PreviewFixtureResource.company_id == context.company.id,
                        PreviewFixtureResource.fixture_key == fixture_key,
                        PreviewFixtureResource.resource_key.in_(keys),
                    )
                )
            ).all()
        )
        by_key = {record.resource_key: record for record in records}
        if set(by_key) != set(keys):
            raise OnboardingConflictError(
                "Fixture release requires a complete ownership manifest."
            )
        for step in steps:
            record = by_key[step.resource_key]
            if not record.active_projection:
                continue
            retain = record.resource_type in AUDIT_RETAINED_TYPES
            if retain and step.release is not None:
                raise OnboardingConflictError(
                    "Timekeeping and Field audit evidence cannot be deleted."
                )
            if not retain and step.release is None:
                raise OnboardingConflictError(
                    "Active fixture resource lacks an owning-domain release operation."
                )
            if step.release is not None:
                await step.release()
            async with session.begin():
                locked = await session.scalar(
                    select(PreviewFixtureResource)
                    .where(
                        PreviewFixtureResource.id == record.id,
                        PreviewFixtureResource.company_id == context.company.id,
                        PreviewFixtureResource.fixture_key == fixture_key,
                    )
                    .with_for_update()
                )
                if locked is None:
                    raise OnboardingConflictError("Fixture ownership changed during release.")
                locked.active_projection = False
                locked.lifecycle = "audit_retained" if retain else "released"
                locked.released_at = datetime.now(timezone.utc)
        return tuple(by_key[key] for key in keys)


preview_fixture_manifest_service = PreviewFixtureManifestService()

from __future__ import annotations

from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext

from .models import AccessAgreementAcceptance, AccessAgreementDocument

SALES_DEMO_AGREEMENT_CODE = "TWELVEHATS_SALES_DEMO_ACCESS"
SALES_DEMO_ROLE = "SALES_DEMO"


class AgreementRequiredError(Exception):
    pass


class AgreementNotConfiguredError(Exception):
    pass


class AgreementValidationError(Exception):
    pass


class AccessAgreementService:
    async def current(self, session: AsyncSession, *, context: AuthorizationContext) -> tuple[AccessAgreementDocument | None, AccessAgreementAcceptance | None]:
        if SALES_DEMO_ROLE not in context.role_codes:
            return None, None
        document = await session.scalar(
            select(AccessAgreementDocument)
            .where(
                AccessAgreementDocument.code == SALES_DEMO_AGREEMENT_CODE,
                AccessAgreementDocument.status == "published",
                AccessAgreementDocument.mandatory.is_(True),
            )
            .order_by(AccessAgreementDocument.version.desc())
        )
        if document is None:
            return None, None
        acceptance = await session.scalar(
            select(AccessAgreementAcceptance).where(
                AccessAgreementAcceptance.user_id == context.user.id,
                AccessAgreementAcceptance.company_id == context.company.id,
                AccessAgreementAcceptance.agreement_id == document.id,
            )
        )
        return document, acceptance

    async def require_access(self, session: AsyncSession, *, context: AuthorizationContext) -> None:
        if SALES_DEMO_ROLE not in context.role_codes:
            return
        document, acceptance = await self.current(session, context=context)
        if document is None:
            raise AgreementNotConfiguredError("Required Sales Demo agreement is not published.")
        if acceptance is None:
            raise AgreementRequiredError("Required Sales Demo agreement acceptance is missing.")

    async def accept(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        agreement_id: UUID,
        version: int,
        acknowledge_reviewed: bool,
        electronic_signature_consent: bool,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AccessAgreementAcceptance:
        if SALES_DEMO_ROLE not in context.role_codes:
            raise AgreementValidationError("This agreement is not required for the active membership.")
        document, existing = await self.current(session, context=context)
        if document is None:
            raise AgreementNotConfiguredError("Required Sales Demo agreement is not published.")
        if existing is not None:
            return existing
        if document.id != agreement_id or document.version != version:
            raise AgreementValidationError("The agreement version is no longer current.")
        if not acknowledge_reviewed or not electronic_signature_consent:
            raise AgreementValidationError("Both affirmative acknowledgments are required.")
        if sha256(document.content.encode("utf-8")).hexdigest() != document.content_sha256:
            raise AgreementValidationError("The agreement document integrity check failed.")
        receipt = AccessAgreementAcceptance(
            user_id=context.user.id,
            company_id=context.company.id,
            agreement_id=document.id,
            agreement_version=document.version,
            agreement_sha256=document.content_sha256,
            recipient_name=context.user.display_name,
            recipient_email=context.user.normalized_email,
            action="I Agree, Electronically Sign & Continue",
            electronic_signature_consent=True,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        session.add(receipt)
        await session.flush()
        return receipt


access_agreement_service = AccessAgreementService()

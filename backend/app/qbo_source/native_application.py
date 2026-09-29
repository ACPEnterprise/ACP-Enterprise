from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.accounting.models import AccountSourceIdentity, PostingSource
from app.accounts_payable.models import VendorBill, VendorSourceMapping
from app.customer_migration.models import CustomerSourceIdentity
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AccountingPermission

from .application_models import QboNativeApplicationRecord, QboNativeReviewItem
from .contracts import QboSourceEnvelope


class QboApplicationError(RuntimeError):
    pass


class ApplicationDisposition(StrEnum):
    APPLIED = "APPLIED"
    BOUND = "BOUND"
    QUARANTINED = "QUARANTINED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"
    REJECTED_WITH_REASON = "REJECTED_WITH_REASON"


@dataclass(frozen=True, slots=True)
class NativeResolution:
    disposition: ApplicationDisposition
    reason_code: str
    explanation: str
    native_type: str | None = None
    native_id: UUID | None = None
    match_basis: str | None = None
    conflicting_fields: tuple[str, ...] = ()
    candidate_native_ids: tuple[str, ...] = ()
    allowed_actions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FamilyDispositionCount:
    source_family: str
    total: int
    applied: int
    bound: int
    quarantined: int
    provider_unavailable: int
    unsupported: int
    rejected: int
    unexplained: int = 0

    @property
    def safe_majority_applied_percentage(self) -> float:
        return round(((self.applied + self.bound) / self.total * 100), 2) if self.total else 0


@dataclass(frozen=True, slots=True)
class ApplicationRunResult:
    processed: int
    created: int
    replayed: int
    family_counts: tuple[FamilyDispositionCount, ...]


@dataclass(frozen=True, slots=True)
class ApplicationLedgerSummary:
    total_dispositions: int
    last_applied_at: datetime | None


_QBO_SOURCE_SYSTEMS = ("quickbooks_online", "qbo")
_REVIEW_ACTIONS = {
    "account": ("MAP_ACCOUNT", "HOLD_FOR_ACCOUNTANT", "IGNORE_SOURCE", "REJECT_WITH_REASON"),
    "customer": ("BIND_EXISTING", "CREATE_NEW", "IGNORE_SOURCE", "REJECT_WITH_REASON"),
    "vendor": ("MAP_VENDOR", "CREATE_NEW", "IGNORE_SOURCE", "REJECT_WITH_REASON"),
    "invoice": ("MAP_CUSTOMER", "MAP_ACCOUNT", "HOLD_FOR_ACCOUNTANT", "IGNORE_SOURCE", "REJECT_WITH_REASON"),
    "payment": ("MAP_CUSTOMER", "MAP_ACCOUNT", "HOLD_FOR_ACCOUNTANT", "IGNORE_SOURCE", "REJECT_WITH_REASON"),
    "bill": ("MAP_VENDOR", "MAP_ACCOUNT", "HOLD_FOR_ACCOUNTANT", "IGNORE_SOURCE", "REJECT_WITH_REASON"),
    "purchase": ("MAP_VENDOR", "MAP_ACCOUNT", "HOLD_FOR_ACCOUNTANT", "IGNORE_SOURCE", "REJECT_WITH_REASON"),
    "deposit": ("MAP_ACCOUNT", "HOLD_FOR_ACCOUNTANT", "IGNORE_SOURCE", "REJECT_WITH_REASON"),
    "transfer": ("MAP_ACCOUNT", "HOLD_FOR_ACCOUNTANT", "IGNORE_SOURCE", "REJECT_WITH_REASON"),
    "journal_entry": ("MAP_ACCOUNT", "HOLD_FOR_ACCOUNTANT", "IGNORE_SOURCE", "REJECT_WITH_REASON"),
    "employee": ("BIND_EXISTING", "CREATE_NEW", "IGNORE_SOURCE", "REJECT_WITH_REASON"),
}


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class QboNativeApplicationService:
    """Apply exact QBO bindings and disposition every other record independently."""

    @staticmethod
    def _authorize(context: AuthorizationContext) -> None:
        if not context.has_permission(AccountingPermission.RECONCILE):
            raise QboApplicationError("Accounting reconciliation authority is required")

    async def apply_clean_majority(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        envelopes: Sequence[tuple[str, QboSourceEnvelope]],
    ) -> ApplicationRunResult:
        self._authorize(context)
        created = replayed = 0
        for envelope_digest, envelope in envelopes:
            async with factory() as session, session.begin():
                was_created = await self._apply_one(
                    session,
                    context=context,
                    envelope_digest=envelope_digest,
                    envelope=envelope,
                )
            created += int(was_created)
            replayed += int(not was_created)
        return ApplicationRunResult(
            processed=len(envelopes),
            created=created,
            replayed=replayed,
            family_counts=await self.family_counts(factory, context=context),
        )

    async def record_provider_unavailable(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        realm_id: str,
        source_family: str,
        reason_code: str,
        explanation: str,
        evidence_digest: str,
        acquired_at: datetime,
    ) -> bool:
        self._authorize(context)
        synthetic_id = f"family-unavailable:{source_family}"
        async with factory() as session, session.begin():
            current = await self._current(
                session, context.company.id, realm_id, source_family, synthetic_id
            )
            if current is not None:
                if current.evidence_digest != evidence_digest:
                    raise QboApplicationError("provider-unavailable evidence changed")
                return False
            session.add(
                QboNativeApplicationRecord(
                    company_id=context.company.id,
                    branch_id=None,
                    realm_id=realm_id,
                    source_family=source_family,
                    provider_record_id=synthetic_id,
                    provider_version=None,
                    source_digest=evidence_digest,
                    evidence_digest=evidence_digest,
                    acquired_at=acquired_at,
                    source_as_of=None,
                    disposition=ApplicationDisposition.PROVIDER_UNAVAILABLE.value,
                    reason_code=reason_code,
                    explanation=explanation,
                    dependency_identities=[],
                    display_evidence={},
                    applied_by_user_id=context.user.id,
                )
            )
            return True

    async def ledger_summary(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
    ) -> ApplicationLedgerSummary:
        self._authorize(context)
        async with factory() as session:
            row = (
                await session.execute(
                    select(
                        func.count(QboNativeApplicationRecord.id),
                        func.max(QboNativeApplicationRecord.applied_at),
                    ).where(
                        QboNativeApplicationRecord.company_id == context.company.id,
                        QboNativeApplicationRecord.superseded_at.is_(None),
                    )
                )
            ).one()
        return ApplicationLedgerSummary(
            total_dispositions=int(row[0] or 0), last_applied_at=row[1]
        )

    async def _apply_one(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        envelope_digest: str,
        envelope: QboSourceEnvelope,
    ) -> bool:
        if envelope.snapshot.environment != "production":
            raise QboApplicationError("only Production QBO evidence may be applied")
        if len(envelope_digest) != 64:
            raise QboApplicationError("source envelope digest is invalid")
        family = envelope.native_entity_type.lower()
        current = await self._current(
            session,
            context.company.id,
            envelope.snapshot.realm_id,
            family,
            envelope.native_id,
        )
        if current is not None and current.source_digest == envelope.raw_sha256:
            return False

        if (
            current is not None
            and current.provider_version == envelope.sync_token
            and current.source_digest != envelope.raw_sha256
        ):
            resolution = NativeResolution(
                ApplicationDisposition.QUARANTINED,
                "provider_version_content_conflict",
                "The same QuickBooks source version has contradictory content.",
                conflicting_fields=("provider_version", "source_digest"),
                allowed_actions=("HOLD_FOR_ACCOUNTANT", "REJECT_WITH_REASON"),
            )
        else:
            resolution = await self._resolve(session, context.company.id, envelope)

        now = datetime.now(timezone.utc)
        version = 1
        if current is not None:
            current.superseded_at = now
            version = current.version + 1
        display = _display_evidence(envelope.raw_payload)
        evidence_digest = _digest(
            {
                "envelope_digest": envelope_digest,
                "source_digest": envelope.raw_sha256,
                "realm_id": envelope.snapshot.realm_id,
                "family": family,
                "provider_record_id": envelope.native_id,
                "provider_version": envelope.sync_token,
                "disposition": resolution.disposition.value,
                "reason_code": resolution.reason_code,
                "native_type": resolution.native_type,
                "native_id": resolution.native_id,
            }
        )
        record = QboNativeApplicationRecord(
            company_id=context.company.id,
            branch_id=(context.active_branch.id if context.active_branch else None),
            realm_id=envelope.snapshot.realm_id,
            source_family=family,
            provider_record_id=envelope.native_id,
            provider_version=envelope.sync_token,
            source_digest=envelope.raw_sha256,
            evidence_digest=evidence_digest,
            acquired_at=envelope.acquired_at,
            source_as_of=envelope.source_updated_at or envelope.source_created_at,
            disposition=resolution.disposition.value,
            reason_code=resolution.reason_code,
            explanation=resolution.explanation,
            native_type=resolution.native_type,
            native_id=resolution.native_id,
            deterministic_match_basis=resolution.match_basis,
            dependency_identities=list(envelope.relationship_ids),
            display_evidence=display,
            version=version,
            applied_by_user_id=context.user.id,
        )
        session.add(record)
        await session.flush()
        if resolution.disposition is ApplicationDisposition.QUARANTINED:
            session.add(
                QboNativeReviewItem(
                    company_id=context.company.id,
                    application_record_id=record.id,
                    source_family=family,
                    provider_record_id=envelope.native_id,
                    reference_number=_optional_display(display, "reference_number"),
                    source_date=_optional_display(display, "source_date"),
                    source_amount=_optional_display(display, "source_amount"),
                    source_entity_names=_display_list(display, "source_entity_names"),
                    candidate_native_ids=list(resolution.candidate_native_ids),
                    conflicting_fields=list(resolution.conflicting_fields),
                    exact_conflict=resolution.explanation,
                    affected_dependents=list(envelope.relationship_ids),
                    allowed_actions=list(
                        resolution.allowed_actions or _REVIEW_ACTIONS.get(family, ("IGNORE_SOURCE", "REJECT_WITH_REASON"))
                    ),
                )
            )
        return True

    async def _resolve(
        self, session: AsyncSession, company_id: UUID, envelope: QboSourceEnvelope
    ) -> NativeResolution:
        family = envelope.native_entity_type.lower()
        realm = envelope.snapshot.realm_id
        if family == "account":
            identity = await session.scalar(
                select(AccountSourceIdentity).where(
                    AccountSourceIdentity.company_id == company_id,
                    AccountSourceIdentity.source_system.in_(_QBO_SOURCE_SYSTEMS),
                    AccountSourceIdentity.source_company_id == realm,
                    AccountSourceIdentity.source_account_id == envelope.native_id,
                )
            )
            if identity:
                return _bound("accounting_account", identity.account_id, "exact_qbo_account_source_identity")
            return _quarantine(family, "account_mapping_required", "No approved native account mapping exists for this QuickBooks account.")
        if family == "customer":
            identity = await session.scalar(
                select(CustomerSourceIdentity).where(
                    CustomerSourceIdentity.company_id == company_id,
                    CustomerSourceIdentity.source_system.in_(_QBO_SOURCE_SYSTEMS),
                    CustomerSourceIdentity.source_customer_id == envelope.native_id,
                )
            )
            if identity:
                return _bound("customer", identity.customer_id, "exact_qbo_customer_source_identity")
            return _quarantine(family, "customer_identity_review_required", "No exact native Customer binding exists; name-only matching is prohibited.")
        if family == "vendor":
            identity = await session.scalar(
                select(VendorSourceMapping).where(
                    VendorSourceMapping.company_id == company_id,
                    VendorSourceMapping.source_system.in_(_QBO_SOURCE_SYSTEMS),
                    VendorSourceMapping.source_company_id == realm,
                    VendorSourceMapping.source_vendor_id == envelope.native_id,
                )
            )
            if identity:
                return _bound("ap_vendor", identity.vendor_id, "exact_qbo_vendor_source_identity")
            return _quarantine(family, "vendor_identity_review_required", "No exact native Vendor binding exists; name-only matching is prohibited.")
        if family == "bill":
            bill = await session.scalar(
                select(VendorBill).where(
                    VendorBill.company_id == company_id,
                    VendorBill.source_system.in_(_QBO_SOURCE_SYSTEMS),
                    VendorBill.source_identity == envelope.native_id,
                )
            )
            if bill:
                return _bound("ap_bill", bill.id, "exact_qbo_bill_source_identity")
            return _quarantine(family, "bill_dependencies_required", "Native bill admission requires an exact Vendor binding and approved account classifications.")
        if family == "journal_entry":
            posting = await session.scalar(
                select(PostingSource).where(
                    PostingSource.company_id == company_id,
                    PostingSource.source_system.in_(_QBO_SOURCE_SYSTEMS),
                    PostingSource.source_type == family,
                    PostingSource.source_identity == envelope.native_id,
                )
            )
            if posting:
                return _bound("accounting_journal", posting.journal_id, "exact_qbo_posting_source_identity")
            return _quarantine(family, "journal_semantics_and_account_mapping_required", "Journal admission requires approved line semantics and exact account mappings.")
        if family in {"invoice", "payment", "purchase", "deposit", "transfer"}:
            return _quarantine(
                family,
                f"{family}_native_admission_contract_required",
                f"The canonical native {family} authority has no approved historical QBO admission contract for this record.",
            )
        if family in {"employee", "time_activity", "tax_payment", "tax_agency"}:
            return NativeResolution(
                ApplicationDisposition.UNSUPPORTED,
                "separate_workforce_or_tax_authority_required",
                "This source family belongs to a separately governed Workforce, Payroll, or tax authority.",
            )
        return NativeResolution(
            ApplicationDisposition.UNSUPPORTED,
            "native_application_not_supported",
            "This QuickBooks source family has no canonical native application contract.",
        )

    async def family_counts(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
    ) -> tuple[FamilyDispositionCount, ...]:
        self._authorize(context)
        async with factory() as session:
            rows = (
                await session.execute(
                    select(
                        QboNativeApplicationRecord.source_family,
                        QboNativeApplicationRecord.disposition,
                        func.count(),
                    )
                    .where(
                        QboNativeApplicationRecord.company_id == context.company.id,
                        QboNativeApplicationRecord.superseded_at.is_(None),
                    )
                    .group_by(
                        QboNativeApplicationRecord.source_family,
                        QboNativeApplicationRecord.disposition,
                    )
                )
            ).all()
        grouped: dict[str, Counter[str]] = {}
        for family, disposition, count in rows:
            grouped.setdefault(family, Counter())[disposition] = count
        return tuple(
            FamilyDispositionCount(
                source_family=family,
                total=sum(counts.values()),
                applied=counts[ApplicationDisposition.APPLIED.value],
                bound=counts[ApplicationDisposition.BOUND.value],
                quarantined=counts[ApplicationDisposition.QUARANTINED.value],
                provider_unavailable=counts[ApplicationDisposition.PROVIDER_UNAVAILABLE.value],
                unsupported=counts[ApplicationDisposition.UNSUPPORTED.value],
                rejected=counts[ApplicationDisposition.REJECTED_WITH_REASON.value],
            )
            for family, counts in sorted(grouped.items())
        )

    async def open_review_items(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        limit: int = 200,
    ) -> tuple[QboNativeReviewItem, ...]:
        self._authorize(context)
        if limit < 1 or limit > 500:
            raise QboApplicationError("review queue limit must be between 1 and 500")
        async with factory() as session:
            return tuple(
                (
                    await session.scalars(
                        select(QboNativeReviewItem)
                        .where(
                            QboNativeReviewItem.company_id == context.company.id,
                            QboNativeReviewItem.state == "OPEN",
                        )
                        .order_by(
                            QboNativeReviewItem.source_family,
                            QboNativeReviewItem.provider_record_id,
                        )
                        .limit(limit)
                    )
                ).all()
            )

    @staticmethod
    async def _current(
        session: AsyncSession,
        company_id: UUID,
        realm_id: str,
        source_family: str,
        provider_record_id: str,
    ) -> QboNativeApplicationRecord | None:
        return await session.scalar(
            select(QboNativeApplicationRecord)
            .where(
                QboNativeApplicationRecord.company_id == company_id,
                QboNativeApplicationRecord.realm_id == realm_id,
                QboNativeApplicationRecord.source_family == source_family,
                QboNativeApplicationRecord.provider_record_id == provider_record_id,
                QboNativeApplicationRecord.superseded_at.is_(None),
            )
            .with_for_update()
        )


def _bound(native_type: str, native_id: UUID, basis: str) -> NativeResolution:
    return NativeResolution(
        ApplicationDisposition.BOUND,
        "exact_native_binding",
        "An exact provider identity is already bound to native authority.",
        native_type=native_type,
        native_id=native_id,
        match_basis=basis,
    )


def _quarantine(family: str, reason: str, explanation: str) -> NativeResolution:
    return NativeResolution(
        ApplicationDisposition.QUARANTINED,
        reason,
        explanation,
        allowed_actions=_REVIEW_ACTIONS.get(family, ("IGNORE_SOURCE", "REJECT_WITH_REASON")),
    )


def _display_evidence(payload: Mapping[str, object]) -> dict[str, object]:
    reference = payload.get("DocNumber") or payload.get("TxnId")
    source_date = payload.get("TxnDate") or payload.get("MetaData")
    amount = payload.get("TotalAmt") or payload.get("Amount") or payload.get("Balance")
    names: list[str] = []
    for key in ("DisplayName", "CompanyName", "PrintOnCheckName"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip() and value not in names:
            names.append(value.strip())
    for key in ("CustomerRef", "VendorRef", "EntityRef"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            name = value.get("name")
            if isinstance(name, str) and name.strip() and name not in names:
                names.append(name.strip())
    return {
        "reference_number": str(reference) if reference is not None else None,
        "source_date": str(source_date) if isinstance(source_date, str) else None,
        "source_amount": str(amount) if amount is not None else None,
        "source_entity_names": names,
    }


def _optional_display(value: Mapping[str, object], key: str) -> str | None:
    item = value.get(key)
    return item if isinstance(item, str) else None


def _display_list(value: Mapping[str, object], key: str) -> list[str]:
    item = value.get(key)
    return [part for part in item if isinstance(part, str)] if isinstance(item, list) else []


qbo_native_application_service = QboNativeApplicationService()

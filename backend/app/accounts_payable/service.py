import hashlib
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.models import (
    Account,
    AccountingPeriod,
    ChartVersion,
    ControlAccountAssignment,
)
from app.accounts_payable.contracts import (
    BillSpec,
    CreditSpec,
    DisbursementSpec,
    PostingReceiptSpec,
    VendorSpec,
)
from app.accounts_payable.errors import APConflict, APNotFound, APValidation
from app.accounts_payable.models import (
    AccountingVendor,
    APAccountMapping,
    APPostingReceipt,
    APSubledgerEntry,
    BillLine,
    BillRevision,
    CreditApplication,
    Disbursement,
    DisbursementApplication,
    DuplicateOverride,
    VendorBill,
    VendorCredit,
    VendorSourceMapping,
)
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.models import AuditRecord

CENT = Decimal("0.01")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def normalize_document(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]", "", value.upper())
    if not normalized:
        raise APValidation("A genuine vendor document number is required.")
    return normalized


class AccountsPayableService:
    async def create_vendor(self, session: AsyncSession, spec: VendorSpec) -> AccountingVendor:
        if not all((spec.code.strip(), spec.legal_name.strip(), spec.display_name.strip(), spec.provenance.strip())):
            raise APValidation("Vendor identity fields are required.")
        async with session.begin():
            existing = await session.scalar(select(AccountingVendor).where(AccountingVendor.company_id == spec.company_id, AccountingVendor.code == spec.code.strip()).with_for_update())
            if existing:
                raise APConflict("Vendor code is already assigned and cannot be reused.")
            vendor = AccountingVendor(company_id=spec.company_id, code=spec.code.strip(), legal_name=spec.legal_name.strip(), display_name=spec.display_name.strip(), provenance=spec.provenance.strip(), default_terms=spec.default_terms, created_by_user_id=spec.actor_user_id)
            session.add(vendor)
            await session.flush()
            self._event(session, EventType.ACCOUNTS_PAYABLE_VENDOR_CREATED, vendor.id, spec.company_id, spec.actor_user_id, {"vendor_id": str(vendor.id)})
            self._audit(session, "accounts_payable.vendor_created", "ap_vendor", vendor.id, spec.company_id, spec.actor_user_id)
        return vendor

    async def map_vendor(self, session: AsyncSession, company_id: UUID, vendor_id: UUID, actor_id: UUID, source_system: str, source_company_id: str, source_vendor_id: str, source_digest: str) -> VendorSourceMapping:
        async with session.begin():
            vendor = await self._vendor(session, company_id, vendor_id, lock=True)
            if vendor.status != "active" or not all(value.strip() for value in (source_system, source_company_id, source_vendor_id, source_digest)):
                raise APValidation("Active vendor and immutable source identity evidence are required.")
            existing = await session.scalar(select(VendorSourceMapping).where(VendorSourceMapping.company_id == company_id, VendorSourceMapping.source_system == source_system, VendorSourceMapping.source_company_id == source_company_id, VendorSourceMapping.source_vendor_id == source_vendor_id).with_for_update())
            if existing:
                if existing.vendor_id != vendor_id or existing.source_digest != source_digest:
                    raise APConflict("Source vendor identity is already mapped differently.")
                return existing
            mapping = VendorSourceMapping(company_id=company_id, vendor_id=vendor_id, source_system=source_system, source_company_id=source_company_id, source_vendor_id=source_vendor_id, source_digest=source_digest, mapped_by_user_id=actor_id)
            session.add(mapping)
            await session.flush()
            self._event(session, EventType.ACCOUNTS_PAYABLE_VENDOR_MAPPED, mapping.id, company_id, actor_id, {"vendor_id": str(vendor_id), "mapping_id": str(mapping.id)})
        return mapping

    async def archive_vendor(self, session: AsyncSession, company_id: UUID, vendor_id: UUID, actor_id: UUID, expected_version: int) -> AccountingVendor:
        async with session.begin():
            vendor = await self._vendor(session, company_id, vendor_id, lock=True)
            if vendor.version != expected_version or vendor.status != "active":
                raise APConflict("Vendor state or version changed.")
            vendor.status = "archived"
            vendor.version += 1
            vendor.archived_at = datetime.now(timezone.utc)
            self._audit(session, "accounts_payable.vendor_archived", "ap_vendor", vendor.id, company_id, actor_id)
        return vendor

    async def create_account_mapping(self, session: AsyncSession, company_id: UUID, actor_id: UUID, mapping_key: str, classification: str, account_id: UUID, effective_from: date, effective_to: date | None, policy_version: str) -> APAccountMapping:
        if classification not in {"expense", "prepaid", "fixed_asset", "inventory_asset", "tax", "freight", "discount", "cash", "clearing", "other"} or not mapping_key.strip() or not policy_version.strip():
            raise APValidation("Complete Finance-approved mapping classification and version are required.")
        if effective_to is not None and effective_to < effective_from:
            raise APValidation("Mapping effective range is invalid.")
        async with session.begin():
            account = await session.scalar(select(Account).where(Account.company_id == company_id, Account.id == account_id, Account.status == "active"))
            if account is None:
                raise APValidation("An active same-Company Accounting Core account is required.")
            overlap = await session.scalar(select(APAccountMapping).where(APAccountMapping.company_id == company_id, APAccountMapping.mapping_key == mapping_key, APAccountMapping.effective_from <= (effective_to or date.max), (APAccountMapping.effective_to.is_(None) | (APAccountMapping.effective_to >= effective_from))))
            if overlap:
                raise APConflict("Account mapping effective range overlaps existing authority.")
            row = APAccountMapping(company_id=company_id, mapping_key=mapping_key, classification=classification, account_id=account_id, effective_from=effective_from, effective_to=effective_to, policy_version=policy_version, approved_by_user_id=actor_id)
            session.add(row)
        return row

    async def create_bill(self, session: AsyncSession, spec: BillSpec) -> VendorBill:
        normalized = normalize_document(spec.vendor_document_number)
        canonical = _digest(spec)
        total = sum((line.net_amount + line.tax_amount for line in spec.lines), Decimal(0)).quantize(CENT)
        if not spec.lines or total <= 0 or spec.due_date < spec.bill_date or not spec.evidence_reference.strip():
            raise APValidation("Complete positive bill lines, valid dates, and evidence are required.")
        async with session.begin():
            await self._validate_core(session, spec.company_id, spec.currency, spec.bill_date)
            await self._vendor(session, spec.company_id, spec.vendor_id, lock=True)
            replay = await session.scalar(select(VendorBill).where(VendorBill.company_id == spec.company_id, VendorBill.source_system == spec.source_system, VendorBill.source_identity == spec.source_identity).with_for_update())
            if replay:
                if replay.source_digest != spec.source_digest:
                    raise APConflict("Source identity conflicts with prior bill evidence.")
                return replay
            duplicate = await session.scalar(select(VendorBill).where(VendorBill.company_id == spec.company_id, VendorBill.vendor_id == spec.vendor_id, VendorBill.normalized_document_number == normalized))
            if duplicate:
                raise APConflict("Hard duplicate vendor bill identity.")
            for line in spec.lines:
                await self._mapping(session, spec.company_id, line.mapping_id, spec.bill_date)
                if line.quantity <= 0 or line.net_amount < 0 or line.tax_amount < 0 or line.branch_id != spec.branch_id:
                    raise APValidation("Bill line amount, quantity, and Branch scope are invalid.")
            count = int(await session.scalar(select(func.count()).select_from(VendorBill).where(VendorBill.company_id == spec.company_id)) or 0)
            bill = VendorBill(company_id=spec.company_id, branch_id=spec.branch_id, vendor_id=spec.vendor_id, bill_number=f"BILL-{count + 1:06d}", vendor_document_number=spec.vendor_document_number.strip(), normalized_document_number=normalized, bill_date=spec.bill_date, received_date=spec.received_date, due_date=spec.due_date, terms_snapshot=spec.terms_snapshot, currency=spec.currency.upper(), total_amount=total, open_amount=total, source_system=spec.source_system, source_identity=spec.source_identity, source_digest=spec.source_digest, evidence_reference=spec.evidence_reference, prepared_by_user_id=spec.actor_user_id, replacement_for_bill_id=spec.replacement_for_bill_id)
            session.add(bill)
            await session.flush()
            revision = BillRevision(company_id=spec.company_id, bill_id=bill.id, revision=1, canonical_digest=canonical, created_by_user_id=spec.actor_user_id)
            session.add(revision)
            await session.flush()
            session.add_all([BillLine(company_id=spec.company_id, revision_id=revision.id, position=index, description=line.description, quantity=line.quantity, unit=line.unit, net_amount=line.net_amount, tax_amount=line.tax_amount, mapping_id=line.mapping_id, branch_id=line.branch_id, purchasing_reference=line.purchasing_reference, receipt_reference=line.receipt_reference) for index, line in enumerate(spec.lines, 1)])
            self._audit(session, "accounts_payable.bill_created", "ap_bill", bill.id, spec.company_id, spec.actor_user_id)
        return bill

    async def submit_bill(self, session: AsyncSession, company_id: UUID, bill_id: UUID, actor_id: UUID, expected_version: int) -> VendorBill:
        return await self._transition(session, company_id, bill_id, actor_id, expected_version, "draft", "submitted")

    async def approve_bill(self, session: AsyncSession, company_id: UUID, bill_id: UUID, actor_id: UUID, expected_version: int) -> VendorBill:
        async with session.begin():
            bill = await self._bill(session, company_id, bill_id, lock=True)
            if bill.status != "submitted" or bill.version != expected_version:
                raise APConflict("Bill state or version changed.")
            if bill.prepared_by_user_id == actor_id:
                raise APValidation("Bill preparer cannot approve the same bill.")
            await self._validate_core(session, company_id, bill.currency, bill.bill_date)
            possible = await session.scalar(select(VendorBill).where(VendorBill.company_id == company_id, VendorBill.vendor_id == bill.vendor_id, VendorBill.id != bill.id, VendorBill.bill_date == bill.bill_date, VendorBill.currency == bill.currency, VendorBill.total_amount == bill.total_amount))
            override = await session.scalar(select(DuplicateOverride).where(DuplicateOverride.company_id == company_id, DuplicateOverride.bill_id == bill.id))
            if possible and override is None:
                raise APConflict("Possible duplicate requires independent override evidence.")
            revision = await session.scalar(select(BillRevision).where(BillRevision.company_id == company_id, BillRevision.bill_id == bill.id, BillRevision.revision == bill.current_revision).with_for_update())
            assert revision is not None
            revision.frozen_at = datetime.now(timezone.utc)
            bill.status = "approved"
            bill.approved_by_user_id = actor_id
            bill.version += 1
            entry = APSubledgerEntry(company_id=company_id, branch_id=bill.branch_id, vendor_id=bill.vendor_id, currency=bill.currency, entry_type="bill", source_id=bill.id, effective_date=bill.bill_date, amount=bill.total_amount, idempotency_key=f"bill:{bill.id}:{bill.current_revision}", evidence_digest=revision.canonical_digest, actor_user_id=actor_id)
            session.add(entry)
            event = self._event(session, EventType.ACCOUNTS_PAYABLE_BILL_APPROVED, bill.id, company_id, actor_id, {"bill_id": str(bill.id), "amount": str(bill.total_amount), "currency": bill.currency})
            await session.flush()
            entry.idempotency_key = f"event:{event.id}"
            self._audit(session, "accounts_payable.bill_approved", "ap_bill", bill.id, company_id, actor_id)
        return bill

    async def authorize_duplicate(self, session: AsyncSession, company_id: UUID, bill_id: UUID, duplicate_bill_id: UUID, requester_id: UUID, reviewer_id: UUID, reason: str, evidence_reference: str) -> DuplicateOverride:
        if requester_id == reviewer_id or not reason.strip() or not evidence_reference.strip():
            raise APValidation("Independent reviewer, reason, and evidence are required.")
        async with session.begin():
            await self._bill(session, company_id, bill_id, lock=True)
            await self._bill(session, company_id, duplicate_bill_id)
            row = DuplicateOverride(company_id=company_id, bill_id=bill_id, duplicate_bill_id=duplicate_bill_id, requester_user_id=requester_id, reviewer_user_id=reviewer_id, reason=reason, evidence_reference=evidence_reference)
            session.add(row)
        return row

    async def issue_credit(self, session: AsyncSession, spec: CreditSpec) -> VendorCredit:
        amount = spec.amount.quantize(CENT)
        if amount <= 0 or not spec.reason.strip():
            raise APValidation("Positive credit and reason are required.")
        async with session.begin():
            await self._vendor(session, spec.company_id, spec.vendor_id)
            await self._validate_core(session, spec.company_id, spec.currency, spec.credit_date)
            await self._mapping(session, spec.company_id, spec.mapping_id, spec.credit_date)
            credit = VendorCredit(company_id=spec.company_id, vendor_id=spec.vendor_id, credit_number=spec.credit_number, credit_date=spec.credit_date, currency=spec.currency.upper(), amount=amount, available_amount=amount, reason=spec.reason, mapping_id=spec.mapping_id, source_system=spec.source_system, source_identity=spec.source_identity, source_digest=spec.source_digest, created_by_user_id=spec.actor_user_id)
            session.add(credit)
            await session.flush()
            session.add(APSubledgerEntry(company_id=spec.company_id, vendor_id=spec.vendor_id, currency=credit.currency, entry_type="credit", source_id=credit.id, effective_date=credit.credit_date, amount=-amount, idempotency_key=f"credit:{credit.id}", evidence_digest=credit.source_digest, actor_user_id=spec.actor_user_id))
            self._event(session, EventType.ACCOUNTS_PAYABLE_VENDOR_CREDIT_ISSUED, credit.id, spec.company_id, spec.actor_user_id, {"credit_id": str(credit.id), "amount": str(amount)})
        return credit

    async def apply_credit(self, session: AsyncSession, company_id: UUID, credit_id: UUID, bill_id: UUID, actor_id: UUID, amount: Decimal, idempotency_key: str) -> CreditApplication:
        amount = amount.quantize(CENT)
        async with session.begin():
            replay = await session.scalar(select(CreditApplication).where(CreditApplication.company_id == company_id, CreditApplication.idempotency_key == idempotency_key))
            if replay:
                return replay
            credit = await session.scalar(select(VendorCredit).where(VendorCredit.company_id == company_id, VendorCredit.id == credit_id).with_for_update())
            bill = await self._bill(session, company_id, bill_id, lock=True)
            if credit is None:
                raise APNotFound("Vendor credit was not found.")
            if credit.vendor_id != bill.vendor_id or credit.currency != bill.currency or amount <= 0 or amount > credit.available_amount or amount > bill.open_amount:
                raise APValidation("Credit application cannot cross vendor/currency or exceed available amounts.")
            credit.available_amount -= amount
            bill.open_amount -= amount
            app = CreditApplication(company_id=company_id, credit_id=credit_id, bill_id=bill_id, amount=amount, idempotency_key=idempotency_key, actor_user_id=actor_id)
            session.add(app)
            await session.flush()
            session.add(APSubledgerEntry(company_id=company_id, branch_id=bill.branch_id, vendor_id=bill.vendor_id, currency=bill.currency, entry_type="credit_application", source_id=app.id, effective_date=datetime.now(timezone.utc).date(), amount=Decimal(0), idempotency_key=f"credit-application:{app.id}", evidence_digest=_digest(app.id), actor_user_id=actor_id))
            self._event(session, EventType.ACCOUNTS_PAYABLE_VENDOR_CREDIT_APPLIED, app.id, company_id, actor_id, {"credit_id": str(credit_id), "bill_id": str(bill_id), "amount": str(amount)})
        return app

    async def unapply_credit(self, session: AsyncSession, company_id: UUID, application_id: UUID, actor_id: UUID, idempotency_key: str) -> CreditApplication:
        async with session.begin():
            existing_entry = await session.scalar(select(APSubledgerEntry).where(APSubledgerEntry.company_id == company_id, APSubledgerEntry.idempotency_key == idempotency_key))
            application = await session.scalar(select(CreditApplication).where(CreditApplication.company_id == company_id, CreditApplication.id == application_id).with_for_update())
            if application is None:
                raise APNotFound("Credit application was not found.")
            if existing_entry:
                return application
            if application.status != "applied":
                raise APConflict("Credit application is already unapplied.")
            credit = await session.scalar(select(VendorCredit).where(VendorCredit.company_id == company_id, VendorCredit.id == application.credit_id).with_for_update())
            bill = await self._bill(session, company_id, application.bill_id, lock=True)
            assert credit is not None
            credit.available_amount += application.amount
            bill.open_amount += application.amount
            application.status = "unapplied"
            session.add(APSubledgerEntry(company_id=company_id, branch_id=bill.branch_id, vendor_id=bill.vendor_id, currency=bill.currency, entry_type="credit_unapplication", source_id=application.id, effective_date=datetime.now(timezone.utc).date(), amount=Decimal(0), idempotency_key=idempotency_key, evidence_digest=_digest(application.id), actor_user_id=actor_id))
        return application

    async def record_disbursement(self, session: AsyncSession, spec: DisbursementSpec) -> Disbursement:
        amount = spec.amount.quantize(CENT)
        if amount <= 0 or spec.recorder_user_id == spec.approver_user_id or not all((spec.external_reference.strip(), spec.source_identity.strip(), spec.evidence_digest.strip())):
            raise APValidation("Verified evidence and distinct recorder/approver are required.")
        async with session.begin():
            await self._vendor(session, spec.company_id, spec.vendor_id)
            await self._validate_core(session, spec.company_id, spec.currency, spec.effective_date)
            row = Disbursement(company_id=spec.company_id, branch_id=spec.branch_id, vendor_id=spec.vendor_id, amount=amount, available_amount=amount, currency=spec.currency.upper(), effective_date=spec.effective_date, method_category=spec.method_category, external_reference=spec.external_reference, source_system=spec.source_system, source_identity=spec.source_identity, evidence_digest=spec.evidence_digest, recorder_user_id=spec.recorder_user_id, approver_user_id=spec.approver_user_id)
            session.add(row)
            await session.flush()
            self._event(session, EventType.ACCOUNTS_PAYABLE_DISBURSEMENT_RECORDED, row.id, spec.company_id, spec.recorder_user_id, {"disbursement_id": str(row.id), "amount": str(amount)})
        return row

    async def apply_disbursement(self, session: AsyncSession, company_id: UUID, disbursement_id: UUID, bill_id: UUID, actor_id: UUID, amount: Decimal, idempotency_key: str) -> DisbursementApplication:
        amount = amount.quantize(CENT)
        async with session.begin():
            replay = await session.scalar(select(DisbursementApplication).where(DisbursementApplication.company_id == company_id, DisbursementApplication.idempotency_key == idempotency_key))
            if replay:
                return replay
            disbursement = await session.scalar(select(Disbursement).where(Disbursement.company_id == company_id, Disbursement.id == disbursement_id).with_for_update())
            bill = await self._bill(session, company_id, bill_id, lock=True)
            if disbursement is None:
                raise APNotFound("Disbursement was not found.")
            if disbursement.vendor_id != bill.vendor_id or disbursement.currency != bill.currency or amount <= 0 or amount > disbursement.available_amount or amount > bill.open_amount:
                raise APValidation("Disbursement cannot cross vendor/currency or over-apply.")
            disbursement.available_amount -= amount
            bill.open_amount -= amount
            bill.status = "paid" if bill.open_amount == 0 else "partially_paid"
            row = DisbursementApplication(company_id=company_id, disbursement_id=disbursement_id, bill_id=bill_id, amount=amount, idempotency_key=idempotency_key, actor_user_id=actor_id)
            session.add(row)
            await session.flush()
            session.add(APSubledgerEntry(company_id=company_id, branch_id=bill.branch_id, vendor_id=bill.vendor_id, currency=bill.currency, entry_type="disbursement", source_id=row.id, effective_date=disbursement.effective_date, amount=-amount, idempotency_key=f"disbursement:{row.id}", evidence_digest=disbursement.evidence_digest, actor_user_id=actor_id))
        return row

    async def reverse_disbursement(self, session: AsyncSession, company_id: UUID, disbursement_id: UUID, actor_id: UUID, reason: str) -> Disbursement:
        if not reason.strip():
            raise APValidation("Disbursement reversal reason is required.")
        async with session.begin():
            row = await session.scalar(select(Disbursement).where(Disbursement.company_id == company_id, Disbursement.id == disbursement_id).with_for_update())
            if row is None:
                raise APNotFound("Disbursement was not found.")
            if row.status != "recorded":
                raise APConflict("Disbursement is already reversed.")
            applications = (await session.scalars(select(DisbursementApplication).where(DisbursementApplication.company_id == company_id, DisbursementApplication.disbursement_id == row.id, DisbursementApplication.status == "applied").with_for_update())).all()
            for application in applications:
                bill = await self._bill(session, company_id, application.bill_id, lock=True)
                bill.open_amount += application.amount
                bill.status = "posted" if bill.accounting_status == "posted" else "approved"
                application.status = "reversed"
            applied = row.amount - row.available_amount
            row.status = "reversed"
            row.available_amount = Decimal(0)
            session.add(APSubledgerEntry(company_id=company_id, branch_id=row.branch_id, vendor_id=row.vendor_id, currency=row.currency, entry_type="disbursement_reversal", source_id=row.id, effective_date=datetime.now(timezone.utc).date(), amount=applied, idempotency_key=f"disbursement-reversal:{row.id}", evidence_digest=_digest(reason), actor_user_id=actor_id))
            self._event(session, EventType.ACCOUNTS_PAYABLE_DISBURSEMENT_REVERSED, row.id, company_id, actor_id, {"disbursement_id": str(row.id), "reason_digest": _digest(reason)})
        return row

    async def reverse_bill(self, session: AsyncSession, company_id: UUID, bill_id: UUID, actor_id: UUID, effective_date: date, reason: str) -> VendorBill:
        if not reason.strip():
            raise APValidation("Reversal reason is required.")
        async with session.begin():
            bill = await self._bill(session, company_id, bill_id, lock=True)
            if bill.status not in {"approved", "posted"} or bill.open_amount != bill.total_amount:
                raise APConflict("Only an unapplied approved/posted bill can be reversed.")
            await self._validate_core(session, company_id, bill.currency, effective_date)
            bill.status = "reversed"
            bill.accounting_status = "reversed"
            bill.open_amount = Decimal(0)
            bill.version += 1
            session.add(APSubledgerEntry(company_id=company_id, branch_id=bill.branch_id, vendor_id=bill.vendor_id, currency=bill.currency, entry_type="bill_reversal", source_id=bill.id, effective_date=effective_date, amount=-bill.total_amount, idempotency_key=f"bill-reversal:{bill.id}:{bill.version}", evidence_digest=_digest(reason), actor_user_id=actor_id))
            self._event(session, EventType.ACCOUNTS_PAYABLE_BILL_REVERSED, bill.id, company_id, actor_id, {"bill_id": str(bill.id), "reason_digest": _digest(reason)})
        return bill

    async def record_posting_receipt(self, session: AsyncSession, spec: PostingReceiptSpec) -> APPostingReceipt:
        if spec.status == "posted" and (spec.journal_id is None or spec.journal_version is None):
            raise APValidation("Posted status requires an Accounting journal receipt.")
        async with session.begin():
            existing = await session.scalar(select(APPostingReceipt).where(APPostingReceipt.company_id == spec.company_id, APPostingReceipt.source_event_id == spec.source_event_id).with_for_update())
            if existing:
                if _digest((existing.status, existing.journal_id, existing.journal_version)) != _digest((spec.status, spec.journal_id, spec.journal_version)):
                    raise APConflict("Contradictory Accounting posting receipt.")
                return existing
            receipt = APPostingReceipt(**spec.__dict__)
            session.add(receipt)
            await session.flush()
            if spec.source_type == "bill":
                bill = await self._bill(session, spec.company_id, spec.source_id, lock=True)
                bill.accounting_status = "posted" if spec.status == "posted" else "reconciliation_required"
                if spec.status == "posted" and bill.status == "approved":
                    bill.status = "posted"
        return receipt

    async def aging(self, session: AsyncSession, company_id: UUID, as_of: date, branch_ids: frozenset[UUID]) -> list[dict[str, object]]:
        rows = (await session.scalars(select(VendorBill).where(VendorBill.company_id == company_id, VendorBill.branch_id.in_(branch_ids), VendorBill.bill_date <= as_of, VendorBill.open_amount > 0).order_by(VendorBill.due_date, VendorBill.bill_number))).all()
        return [{"vendor_id": row.vendor_id, "bill_id": row.id, "bill_number": row.bill_number, "bill_date": row.bill_date, "due_date": row.due_date, "original_amount": row.total_amount, "open_amount": row.open_amount, "currency": row.currency, "days_past_due": max(0, (as_of - row.due_date).days), "status": row.status} for row in rows]

    async def _transition(self, session: AsyncSession, company_id: UUID, bill_id: UUID, actor_id: UUID, expected_version: int, expected: str, target: str) -> VendorBill:
        async with session.begin():
            bill = await self._bill(session, company_id, bill_id, lock=True)
            if bill.status != expected or bill.version != expected_version:
                raise APConflict("Bill state or version changed.")
            bill.status = target
            bill.version += 1
            bill.updated_at = datetime.now(timezone.utc)
            self._audit(session, f"accounts_payable.bill_{target}", "ap_bill", bill.id, company_id, actor_id)
        return bill

    async def _validate_core(self, session: AsyncSession, company_id: UUID, currency: str, effective_date: date) -> None:
        chart = await session.scalar(select(ChartVersion).where(ChartVersion.company_id == company_id, ChartVersion.is_active.is_(True)))
        if chart is None or chart.currency != currency.upper():
            raise APValidation("Active Accounting Core functional currency is required.")
        period = await session.scalar(select(AccountingPeriod).where(AccountingPeriod.company_id == company_id, AccountingPeriod.start_date <= effective_date, AccountingPeriod.end_date >= effective_date))
        if period is None or period.status != "open":
            raise APValidation("Accounting effective date must be in an open period.")
        control = await session.scalar(select(ControlAccountAssignment).where(ControlAccountAssignment.company_id == company_id, ControlAccountAssignment.control_role == "accounts_payable", ControlAccountAssignment.effective_from <= effective_date, (ControlAccountAssignment.effective_to.is_(None) | (ControlAccountAssignment.effective_to >= effective_date))))
        if control is None:
            raise APValidation("An effective AP control assignment is required.")

    async def _mapping(self, session: AsyncSession, company_id: UUID, mapping_id: UUID, effective_date: date) -> APAccountMapping:
        mapping = await session.scalar(select(APAccountMapping).join(Account, Account.id == APAccountMapping.account_id).where(APAccountMapping.company_id == company_id, APAccountMapping.id == mapping_id, APAccountMapping.effective_from <= effective_date, (APAccountMapping.effective_to.is_(None) | (APAccountMapping.effective_to >= effective_date)), Account.company_id == company_id, Account.status == "active"))
        if mapping is None:
            raise APValidation("An active, effective, same-Company account mapping is required.")
        return mapping

    async def _vendor(self, session: AsyncSession, company_id: UUID, vendor_id: UUID, lock: bool = False) -> AccountingVendor:
        query = select(AccountingVendor).where(AccountingVendor.company_id == company_id, AccountingVendor.id == vendor_id)
        vendor = await session.scalar(query.with_for_update() if lock else query)
        if vendor is None:
            raise APNotFound("Accounting vendor was not found.")
        return vendor

    async def _bill(self, session: AsyncSession, company_id: UUID, bill_id: UUID, lock: bool = False) -> VendorBill:
        query = select(VendorBill).where(VendorBill.company_id == company_id, VendorBill.id == bill_id)
        bill = await session.scalar(query.with_for_update() if lock else query)
        if bill is None:
            raise APNotFound("Vendor bill was not found.")
        return bill

    def _event(self, session: AsyncSession, event_type: EventType, aggregate_id: UUID, company_id: UUID, actor_id: UUID, payload: dict[str, object]):
        return BusinessEventService.stage(session, BusinessEventCreate(event_type=event_type, entity_type="accounts_payable", entity_id=aggregate_id, company_id=company_id, user_id=actor_id, payload=payload))

    def _audit(self, session: AsyncSession, action: str, resource_type: str, resource_id: UUID, company_id: UUID, actor_id: UUID) -> None:
        session.add(AuditRecord(id=uuid4(), action=action, outcome="success", actor_user_id=actor_id, company_id=company_id, resource_type=resource_type, resource_id=resource_id, correlation_id=uuid4(), details={}, occurred_at=datetime.now(timezone.utc)))


accounts_payable_service = AccountsPayableService()

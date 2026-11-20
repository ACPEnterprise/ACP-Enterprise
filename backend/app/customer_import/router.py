"""Tenant-scoped customer file import and admission API."""

from __future__ import annotations

import json
import hashlib
from collections import Counter
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_import.engine import (
    CustomerImportEngine,
    CustomerImportMapping,
    CustomerImportScope,
    ImportSchemaError,
    _csv_rows,
    _xlsx_rows,
)
from app.customer_import.models import CustomerImportAuditEvent, CustomerImportBatch, CustomerImportRow
from app.customer_migration.models import CustomerMigrationRun, CustomerSourceIdentity
from app.customers.models import Customer, CustomerContact, ServiceLocation
from app.customers.normalization import build_normalized_address, normalize_email, normalize_phone, normalize_search_text
from app.customers.schemas import ContactCreate, CustomerCreate, CustomerStatus, CustomerType, ServiceLocationCreate
from app.customers.service import CustomerService
from app.database.session import get_database_session
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import CustomerPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/customer-import", tags=["Customer Import"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
CustomerManager = Annotated[AuthorizationContext, Depends(require_permission(CustomerPermission.MANAGE))]

class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImportBatchResponse(StrictSchema):
    batch_id: UUID
    status: str
    source_rows: int
    ready: int
    duplicates: int
    held: int
    rejected: int
    reused: bool
    source_sha256: str
    mapping_sha256: str
    file_format: str


class ImportAdmissionResponse(StrictSchema):
    batch_id: UUID
    status: str
    created: int
    matched: int
    replayed: int
    held: int
    rejected: int
    processed: int


class ImportRowResponse(StrictSchema):
    row_number: int
    source_record_id: str
    disposition: str
    reason_code: str | None
    processed: bool


class ImportBatchDetailResponse(ImportBatchResponse):
    rows: list[ImportRowResponse]


def _source_system(provider: str, namespace: str) -> str:
    """Migration lineage key; source identities remain namespace-specific."""
    value = f"{provider}:{namespace}"
    if len(value) <= 50:
        return value
    return f"{provider[:12]}:{hashlib.sha256(value.encode()).hexdigest()[:36]}"


def _requires_qualified_hcp_admission(provider: str, namespace: str) -> bool:
    return provider.lower() == "housecall_pro" and namespace.lower() == "housecall_pro_source4"


def _identity_systems(provider: str, namespace: str) -> tuple[str, ...]:
    """Return the new scoped key plus only the known legacy HCP key."""
    scoped = _source_system(provider, namespace)
    if provider.lower() == "housecall_pro":
        # Preserve exact native identities written by the earlier SOURCE.4
        # admission while binding a replay to the current explicit namespace.
        return (scoped, namespace.lower(), "housecall_pro_source4")
    return (scoped,)


def _mapping(value: str, *, body: bytes, filename: str) -> CustomerImportMapping:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Import field mapping is not valid JSON.") from error
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Import field mapping must be an object.")
    if not payload:
        try:
            _, rows = _csv_rows(body) if filename.lower().endswith(".csv") else _xlsx_rows(body)
            headers = tuple(rows[0]) if rows else ()
        except ImportSchemaError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
        normalized = {" ".join(header.strip().lower().replace("_", " ").replace("-", " ").split()): header for header in headers}
        def find(*names: str) -> str | None:
            return next((normalized[name] for name in names if name in normalized), None)
        source_header = find("id", "customer id", "source id", "source customer id")
        if source_header is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The file needs a source customer ID column.")
        inferred = {
            key: header for key, header in {
                "display_name": find("display name", "customer name", "name"),
                "first_name": find("first name"),
                "last_name": find("last name"),
                "company_name": find("company", "company name"),
                "email": find("email", "emails"),
                "phone": find("phone", "mobile number", "mobile phone", "home number", "work number"),
                "address": find("service address", "address", "street address"),
                "city": find("service city", "city"),
                "state": find("service state", "state"),
                "postal_code": find("service postal code", "postal code", "zip", "zip code"),
            }.items() if header is not None
        }
        payload = {"source_record_id": source_header, **inferred}
    if not isinstance(payload.get("source_record_id"), str):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A source record ID mapping is required.")
    source_id = payload.pop("source_record_id")
    try:
        return CustomerImportMapping(source_record_id=source_id, fields=payload)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


def _batch_response(batch: CustomerImportBatch, *, reused: bool = False) -> ImportBatchResponse:
    return ImportBatchResponse(
        batch_id=batch.id,
        status=batch.status,
        source_rows=batch.row_count,
        ready=batch.ready_count,
        duplicates=batch.duplicate_count,
        held=batch.held_count,
        rejected=batch.rejected_count,
        reused=reused,
        source_sha256=batch.source_sha256,
        mapping_sha256=batch.mapping_sha256,
        file_format=batch.file_format,
    )


def _customer_from_payload(payload: dict[str, str]) -> tuple[CustomerCreate, ContactCreate | None, ServiceLocationCreate | None]:
    first = payload.get("first_name", "").strip()
    last = payload.get("last_name", "").strip()
    company = payload.get("company_name", "").strip()
    display = payload.get("display_name", "").strip() or company or " ".join(value for value in (first, last) if value)
    if not display:
        raise ValueError("missing_customer_name")
    customer_type = CustomerType.COMMERCIAL if company else CustomerType.RESIDENTIAL
    contact = None
    if first and last and (payload.get("email") or payload.get("phone")):
        contact = ContactCreate(
            first_name=first,
            last_name=last,
            email=payload.get("email") or None,
            mobile_phone=payload.get("phone") or None,
            is_preferred=True,
        )
    address_values = tuple(payload.get(key, "").strip() for key in ("address", "city", "state", "postal_code"))
    location = None
    if any(address_values):
        if not all(address_values):
            raise ValueError("incomplete_service_address")
        location = ServiceLocationCreate(
            address=address_values[0], city=address_values[1], state=address_values[2], postal_code=address_values[3], is_primary=True
        )
    return CustomerCreate(
        customer_type=customer_type,
        display_name=display,
        legal_name=company or None,
        status=CustomerStatus.ACTIVE,
    ), contact, location


async def _match_existing(session: AsyncSession, company_id: UUID, payload: dict[str, str]) -> tuple[UUID | None, bool]:
    signals: dict[UUID, set[str]] = {}
    name = normalize_search_text(payload.get("display_name") or payload.get("company_name") or " ".join((payload.get("first_name", ""), payload.get("last_name", ""))).strip())
    if name:
        ids = (await session.scalars(select(Customer.id).where(Customer.company_id == company_id, Customer.archived_at.is_(None), Customer.normalized_name == name))).all()
        for item in ids:
            signals.setdefault(item, set()).add("name")
    email = payload.get("email", "").strip()
    if email:
        ids = (await session.scalars(select(CustomerContact.customer_id).join(Customer, Customer.id == CustomerContact.customer_id).where(Customer.company_id == company_id, CustomerContact.normalized_email == normalize_email(email)))).all()
        for item in ids:
            signals.setdefault(item, set()).add("email")
    phone = payload.get("phone", "").strip()
    if phone:
        normalized = normalize_phone(phone)
        ids = (await session.scalars(select(CustomerContact.customer_id).join(Customer, Customer.id == CustomerContact.customer_id).where(Customer.company_id == company_id, (CustomerContact.normalized_mobile_phone == normalized) | (CustomerContact.normalized_office_phone == normalized)))).all()
        for item in ids:
            signals.setdefault(item, set()).add("phone")
    address = tuple(payload.get(key, "").strip() for key in ("address", "city", "state", "postal_code"))
    if all(address):
        normalized_address = build_normalized_address(address[0], None, address[1], address[2], address[3])
        ids = (await session.scalars(select(ServiceLocation.customer_id).join(Customer, Customer.id == ServiceLocation.customer_id).where(Customer.company_id == company_id, ServiceLocation.normalized_address == normalized_address))).all()
        for item in ids:
            signals.setdefault(item, set()).add("address")
    if not signals:
        return None, False
    best = max(len(values) for values in signals.values())
    candidates = [customer_id for customer_id, values in signals.items() if len(values) == best]
    if best >= 2 and len(candidates) == 1:
        return candidates[0], False
    return None, True


def _source_identity_values(payload: dict[str, str]) -> tuple[str, str, str, str]:
    """Return normalized source identity fields used by safe-new admission."""
    name = normalize_search_text(
        payload.get("display_name")
        or payload.get("company_name")
        or " ".join((payload.get("first_name", ""), payload.get("last_name", ""))).strip()
    )
    try:
        email = normalize_email(payload.get("email", "").strip()) if payload.get("email", "").strip() else ""
    except ValueError:
        email = ""
    try:
        phone = normalize_phone(payload.get("phone", "").strip()) if payload.get("phone", "").strip() else ""
    except ValueError:
        phone = ""
    address = tuple(payload.get(key, "").strip() for key in ("address", "city", "state", "postal_code"))
    normalized_address = build_normalized_address(address[0], None, address[1], address[2], address[3]) if all(address) else ""
    return name, email, phone, normalized_address


def _source_identity_counts(source_payloads: list[dict[str, str]]) -> tuple[Counter[str], Counter[str], Counter[tuple[str, str]]]:
    email_counts: Counter[str] = Counter()
    phone_counts: Counter[str] = Counter()
    name_address_counts: Counter[tuple[str, str]] = Counter()
    for payload in source_payloads:
        name, email, phone, address = _source_identity_values(payload)
        if email:
            email_counts[email] += 1
        if phone:
            phone_counts[phone] += 1
        if name and address:
            name_address_counts[(name, address)] += 1
    return email_counts, phone_counts, name_address_counts


def _verified_new_source_identity(payload: dict[str, str], source_counts: tuple[Counter[str], Counter[str], Counter[tuple[str, str]]]) -> bool:
    """Allow a new customer only with complete, unique source evidence.

    Missing crosswalk evidence is not enough by itself. A source row must have
    a complete name/contact/address identity, a unique contact value within the
    source batch, and a unique normalized name/address pair within that batch.
    """
    name, email, phone, address = _source_identity_values(payload)
    if not name or not email or not phone or not address:
        return False
    email_counts, phone_counts, name_address_counts = source_counts
    email_count = email_counts[email]
    phone_count = phone_counts[phone]
    name_address_count = name_address_counts[(name, address)]
    return email_count == 1 and phone_count == 1 and name_address_count == 1


@router.post("/batches", response_model=ImportBatchResponse, status_code=status.HTTP_201_CREATED)
async def stage_customer_import(
    context: CustomerManager,
    session: DatabaseSession,
    response: Response,
    body: bytes = Body(...),
    filename: Annotated[str, Header(alias="X-Customer-Import-Filename", min_length=1, max_length=255)] = "customers.csv",
    provider: Annotated[str, Header(alias="X-Customer-Import-Provider", min_length=1, max_length=80)] = "file",
    namespace: Annotated[str, Header(alias="X-Customer-Import-Namespace", min_length=1, max_length=80)] = "file",
    mapping_header: Annotated[str, Header(alias="X-Customer-Import-Mapping", min_length=2)] = "{}",
) -> ImportBatchResponse:
    if context.active_branch is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An active Branch is required for customer import.")
    try:
        mapping = _mapping(mapping_header, body=body, filename=filename)
        scope = CustomerImportScope(context.company.id, context.active_branch.id, provider, namespace)
        result = CustomerImportEngine().stage(body, filename=filename, scope=scope, mapping=mapping)
    except (ImportSchemaError, ValueError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    existing = await session.scalar(select(CustomerImportBatch).where(
        CustomerImportBatch.company_id == context.company.id,
        CustomerImportBatch.branch_id == context.active_branch.id,
        CustomerImportBatch.source_provider == scope.source_provider,
        CustomerImportBatch.source_namespace == scope.source_namespace,
        CustomerImportBatch.source_sha256 == result.source_sha256,
        CustomerImportBatch.mapping_sha256 == result.mapping_sha256,
    ))
    if existing is not None:
        response.headers["Cache-Control"] = "private, no-store"
        return _batch_response(existing, reused=True)
    batch = CustomerImportBatch(
        batch_key=result.batch_key,
        company_id=context.company.id, branch_id=context.active_branch.id,
        source_provider=scope.source_provider, source_namespace=scope.source_namespace,
        source_sha256=result.source_sha256, mapping_sha256=result.mapping_sha256,
        schema_version=result.schema_version, file_format=result.file_format,
        row_count=result.counts.source_rows, ready_count=result.counts.ready,
        duplicate_count=result.counts.duplicates, held_count=result.counts.held,
        rejected_count=result.counts.rejected, cursor_row=1, created_by_user_id=context.user.id,
    )
    session.add(batch)
    try:
        await session.flush()
    except IntegrityError:
        # Another request may have staged the same immutable artifact between
        # the read and insert. Do not create a second batch or swallow another
        # database error.
        await session.rollback()
        existing = await session.scalar(select(CustomerImportBatch).where(
            CustomerImportBatch.company_id == context.company.id,
            CustomerImportBatch.branch_id == context.active_branch.id,
            CustomerImportBatch.source_provider == scope.source_provider,
            CustomerImportBatch.source_namespace == scope.source_namespace,
            CustomerImportBatch.source_sha256 == result.source_sha256,
            CustomerImportBatch.mapping_sha256 == result.mapping_sha256,
        ))
        if existing is None:
            raise
        response.headers["Cache-Control"] = "private, no-store"
        return _batch_response(existing, reused=True)
    for row in result.rows:
        session.add(CustomerImportRow(
            batch_id=batch.id, company_id=context.company.id, branch_id=context.active_branch.id,
            row_number=row.row_number, source_record_id=row.source_record_id,
            source_identity_key=row.source_identity_key, source_row_sha256=row.source_row_sha256,
            disposition=row.disposition, reason_code=row.reason_code, payload=dict(row.payload),
            validation_errors=list(row.validation_errors),
        ))
    session.add(CustomerImportAuditEvent(
        batch_id=batch.id, company_id=context.company.id, branch_id=context.active_branch.id,
        event_key="staged", event_type="customer_import_staged", actor_user_id=context.user.id,
        details={"counts": result.counts.as_dict(), "filename": filename},
    ))
    audit_service.stage(session, AuditEntry(
        action="customer_import.staged", resource_type="customer_import_batch", resource_id=batch.id,
        actor_user_id=context.user.id, company_id=context.company.id, branch_id=context.active_branch.id,
        details={"source_sha256": result.source_sha256, "source_rows": result.counts.source_rows},
    ))
    # The request-scoped session does not auto-commit. A successful staging
    # response must therefore be durable before the caller can safely retry or
    # resume the batch.
    await session.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return _batch_response(batch)


@router.get("/batches/{batch_id}", response_model=ImportBatchDetailResponse)
async def get_customer_import_batch(batch_id: UUID, context: CustomerManager, session: DatabaseSession) -> ImportBatchDetailResponse:
    if context.active_branch is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An active Branch is required for customer import.")
    batch = await session.scalar(select(CustomerImportBatch).where(CustomerImportBatch.id == batch_id, CustomerImportBatch.company_id == context.company.id, CustomerImportBatch.branch_id == context.active_branch.id))
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import batch was not found.")
    rows = (await session.scalars(select(CustomerImportRow).where(CustomerImportRow.batch_id == batch.id).order_by(CustomerImportRow.row_number))).all()
    return ImportBatchDetailResponse(**_batch_response(batch).model_dump(), rows=[ImportRowResponse(row_number=row.row_number, source_record_id=row.source_record_id, disposition=row.disposition, reason_code=row.reason_code, processed=row.processed) for row in rows])


@router.post("/batches/{batch_id}/admit", response_model=ImportAdmissionResponse)
async def admit_customer_import(batch_id: UUID, context: CustomerManager, session: DatabaseSession, limit: Annotated[int, Query(ge=1, le=10000)] = 10000) -> ImportAdmissionResponse:
    if context.active_branch is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An active Branch is required for customer import.")
    batch = await session.scalar(select(CustomerImportBatch).where(CustomerImportBatch.id == batch_id, CustomerImportBatch.company_id == context.company.id, CustomerImportBatch.branch_id == context.active_branch.id).with_for_update())
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import batch was not found.")
    if _requires_qualified_hcp_admission(batch.source_provider, batch.source_namespace):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "housecall_pro_source4 must use the qualified master-bound HCP admission path.",
        )
    run = None
    if batch.migration_run_id is not None:
        run = await session.get(CustomerMigrationRun, batch.migration_run_id, with_for_update=True)
    if run is None:
        run = CustomerMigrationRun(company_id=context.company.id, branch_id=context.active_branch.id, initiated_by_user_id=context.user.id, source_system=_source_system(batch.source_provider, batch.source_namespace), source_sha256=batch.source_sha256, mode="import", status="running", source_count=0, accepted_count=0, rejected_count=0, duplicate_count=0, unresolved_count=0)
        session.add(run)
        await session.flush()
        batch.migration_run_id = run.id
    all_ready_rows = (await session.scalars(select(CustomerImportRow).where(CustomerImportRow.batch_id == batch.id, CustomerImportRow.processed.is_(False), CustomerImportRow.disposition == "ready").order_by(CustomerImportRow.row_number))).all()
    rows = all_ready_rows[:limit]
    source_payloads = [row.payload for row in all_ready_rows]
    source_counts = _source_identity_counts(source_payloads)
    created = matched = replayed = held = rejected = 0
    customer_service = CustomerService()
    identity_system = _source_system(batch.source_provider, batch.source_namespace)
    identity_systems = _identity_systems(batch.source_provider, batch.source_namespace)
    for row in rows:
        row.attempt_count += 1
        await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"customer-import:{context.company.id}:{batch.source_provider}:{batch.source_namespace}:{row.source_record_id}"))))
        identity = await session.scalar(select(CustomerSourceIdentity).where(CustomerSourceIdentity.company_id == context.company.id, CustomerSourceIdentity.branch_id == context.active_branch.id, CustomerSourceIdentity.source_system.in_(identity_systems), CustomerSourceIdentity.source_customer_id == row.source_record_id))
        if identity is not None:
            if identity.source_system != identity_system:
                scoped_identity = await session.scalar(select(CustomerSourceIdentity).where(CustomerSourceIdentity.company_id == context.company.id, CustomerSourceIdentity.branch_id == context.active_branch.id, CustomerSourceIdentity.source_system == identity_system, CustomerSourceIdentity.source_customer_id == row.source_record_id))
                if scoped_identity is None:
                    session.add(CustomerSourceIdentity(company_id=context.company.id, branch_id=context.active_branch.id, customer_id=identity.customer_id, source_system=identity_system, source_customer_id=row.source_record_id, first_run_id=run.id))
            row.disposition = "duplicate"; row.processed = True; row.processed_at = datetime.now(timezone.utc); replayed += 1; run.source_count += 1; run.duplicate_count += 1; continue
        try:
            customer_data, contact_data, location_data = _customer_from_payload(row.payload)
            customer_id, ambiguous = await _match_existing(session, context.company.id, row.payload)
            if ambiguous:
                row.disposition = "held"; row.reason_code = "ambiguous_existing_customer_match"; row.processed = True; row.processed_at = datetime.now(timezone.utc); held += 1; run.source_count += 1; run.unresolved_count += 1; continue
            if customer_id is None:
                if not _verified_new_source_identity(row.payload, source_counts):
                    row.disposition = "held"; row.reason_code = "unverified_new_customer_identity"; row.processed = True; row.processed_at = datetime.now(timezone.utc); held += 1; run.source_count += 1; run.unresolved_count += 1; continue
                customer = await customer_service.stage_migrated_customer(session, context=context, customer_data=customer_data, contact_data=contact_data, service_location_data=location_data, billing_address_data=None)
                customer_id = customer.id; created += 1
            else:
                matched += 1
            existing_target_identity = await session.scalar(
                select(CustomerSourceIdentity.id).where(
                    CustomerSourceIdentity.company_id == context.company.id,
                    CustomerSourceIdentity.branch_id == context.active_branch.id,
                    CustomerSourceIdentity.source_system == identity_system,
                    CustomerSourceIdentity.customer_id == customer_id,
                )
            )
            if existing_target_identity is not None:
                row.disposition = "held"; row.reason_code = "duplicate_existing_customer_target"; row.processed = True; row.processed_at = datetime.now(timezone.utc); matched -= 1; held += 1; run.source_count += 1; run.unresolved_count += 1; continue
            session.add(CustomerSourceIdentity(company_id=context.company.id, branch_id=context.active_branch.id, customer_id=customer_id, source_system=identity_system, source_customer_id=row.source_record_id, first_run_id=run.id))
            row.processed = True; row.processed_at = datetime.now(timezone.utc); run.source_count += 1; run.accepted_count += 1
        except (ValueError, TypeError) as error:
            row.disposition = "held"; row.reason_code = str(error)[:80]; row.processed = True; row.processed_at = datetime.now(timezone.utc); held += 1; run.source_count += 1; run.unresolved_count += 1
    remaining_ready = await session.scalar(select(func.count()).select_from(CustomerImportRow).where(CustomerImportRow.batch_id == batch.id, CustomerImportRow.disposition == "ready", CustomerImportRow.processed.is_(False)))
    run.status = "completed" if not remaining_ready else "running"
    run.completed_at = datetime.now(timezone.utc) if run.status == "completed" else None
    if not remaining_ready:
        batch.status = "completed"
        batch.migration_run_id = run.id
    else:
        batch.status = "paused"
        batch.cursor_row = max((row.row_number for row in rows), default=batch.cursor_row) + 1
    batch.ready_count = max(0, batch.ready_count - created - matched - replayed - held)
    batch.duplicate_count += replayed
    batch.held_count += held
    session.add(CustomerImportAuditEvent(batch_id=batch.id, company_id=context.company.id, branch_id=context.active_branch.id, event_key=f"admit:{run.id}", event_type="customer_import_admitted", actor_user_id=context.user.id, details={"created": created, "matched": matched, "replayed": replayed, "held": held}))
    await session.commit()
    return ImportAdmissionResponse(batch_id=batch.id, status=batch.status, created=created, matched=matched, replayed=replayed, held=held, rejected=rejected, processed=len(rows))

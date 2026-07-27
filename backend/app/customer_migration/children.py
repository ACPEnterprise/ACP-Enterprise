import csv
import hashlib
import io
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customer_migration.housecall_pro import (
    SOURCE_SYSTEM,
    MigrationReport,
    UnresolvedRowError,
    normalized_header,
)
from app.customer_migration.models import (
    CustomerContactSourceIdentity,
    CustomerMigrationException,
    CustomerMigrationProgress,
    CustomerMigrationRun,
    CustomerSourceIdentity,
    ServiceLocationSourceIdentity,
    utc_now,
)
from app.customers.models import CustomerContact, ServiceLocation
from app.customers.normalization import (
    build_normalized_address,
    normalize_email,
    normalize_phone,
)
from app.customers.schemas import ContactCreate, ServiceLocationCreate
from app.customers.service import CustomerService
from app.platform.permissions.authorization import AuthorizationContext

EntityType = Literal["contact", "service_location"]
Disposition = Literal["accepted", "rejected", "duplicate", "unresolved"]
ProgressCallback = Callable[["MigrationProgress"], None]

CONTACT_HEADERS = frozenset(
    {
        "contact_id",
        "customer_id",
        "first_name",
        "last_name",
        "role",
        "email",
        "mobile_number",
        "work_number",
        "preferred",
        "active",
        "notes",
    }
)
LOCATION_HEADERS = frozenset(
    {
        "service_location_id",
        "customer_id",
        "nickname",
        "address",
        "address_line_2",
        "city",
        "state",
        "postal_code",
        "country",
        "service_address_notes",
        "active",
    }
)


@dataclass(frozen=True)
class MigrationProgress:
    run_id: str
    entity_type: EntityType
    source: int
    processed: int
    accepted: int
    rejected: int
    duplicate: int
    unresolved: int


@dataclass(frozen=True)
class ParsedContact:
    source_id: str
    source_customer_id: str
    data: ContactCreate


@dataclass(frozen=True)
class ParsedServiceLocation:
    source_id: str
    source_customer_id: str
    data: ServiceLocationCreate


def _optional(row: dict[str, str], key: str) -> str | None:
    value = row.get(key, "").strip()
    return value or None


def _required_identifier(row: dict[str, str], key: str) -> str:
    value = _optional(row, key)
    if value is None:
        raise UnresolvedRowError(f"{key} is required for safe referential integrity")
    if len(value) > 191:
        raise ValueError(f"{key} exceeds 191 characters")
    return value


def _boolean(row: dict[str, str], key: str, *, default: bool) -> bool:
    value = _optional(row, key)
    if value is None:
        return default
    normalized = value.lower()
    if normalized in {"true", "t", "yes", "y", "1"}:
        return True
    if normalized in {"false", "f", "no", "n", "0"}:
        return False
    raise ValueError(f"{key} must be a recognized boolean")


def parse_contact(row: dict[str, str]) -> ParsedContact:
    return ParsedContact(
        source_id=_required_identifier(row, "contact_id"),
        source_customer_id=_required_identifier(row, "customer_id"),
        data=ContactCreate(
            first_name=_optional(row, "first_name") or "",
            last_name=_optional(row, "last_name") or "",
            title=_optional(row, "role"),
            email=_optional(row, "email"),
            mobile_phone=_optional(row, "mobile_number"),
            office_phone=_optional(row, "work_number"),
            is_preferred=_boolean(row, "preferred", default=False),
            active=_boolean(row, "active", default=True),
            notes=_optional(row, "notes"),
        ),
    )


def parse_service_location(row: dict[str, str]) -> ParsedServiceLocation:
    return ParsedServiceLocation(
        source_id=_required_identifier(row, "service_location_id"),
        source_customer_id=_required_identifier(row, "customer_id"),
        data=ServiceLocationCreate(
            nickname=_optional(row, "nickname"),
            address=_optional(row, "address") or "",
            address_line_2=_optional(row, "address_line_2"),
            city=_optional(row, "city") or "",
            state=_optional(row, "state") or "",
            postal_code=_optional(row, "postal_code") or "",
            country=_optional(row, "country") or "US",
            property_notes=_optional(row, "service_address_notes"),
            active=_boolean(row, "active", default=True),
        ),
    )


def _read_rows(path: Path, supported_headers: frozenset[str]) -> list[dict[str, str]]:
    raw = path.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if reader.fieldnames is None:
        raise ValueError(f"{path.name} has no header")
    headers = [normalized_header(value) for value in reader.fieldnames]
    if len(set(headers)) != len(headers):
        raise ValueError(f"{path.name} has duplicate normalized headers")
    unknown = set(headers) - supported_headers
    if unknown:
        raise ValueError(f"Unsupported columns in {path.name}: {sorted(unknown)}")
    return [
        {normalized_header(key): value or "" for key, value in row.items()}
        for row in reader
    ]


class HousecallProCustomerChildrenMigration:
    """Import plural Contact and Service Location streams after Customer identity."""

    def __init__(self, customer_service: CustomerService | None = None) -> None:
        self.customer_service = customer_service or CustomerService()

    @staticmethod
    async def _parent_identity(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        source_customer_id: str,
    ) -> CustomerSourceIdentity | None:
        assert context.active_branch is not None
        return await session.scalar(
            select(CustomerSourceIdentity).where(
                CustomerSourceIdentity.company_id == context.company.id,
                CustomerSourceIdentity.branch_id == context.active_branch.id,
                CustomerSourceIdentity.source_system == SOURCE_SYSTEM,
                CustomerSourceIdentity.source_customer_id == source_customer_id,
            )
        )

    @staticmethod
    async def _contact_match_count(
        session: AsyncSession,
        *,
        customer_id: UUID,
        data: ContactCreate,
    ) -> int:
        signals = [
            func.lower(CustomerContact.first_name) == data.first_name.lower(),
            func.lower(CustomerContact.last_name) == data.last_name.lower(),
        ]
        strong_signals = []
        if data.email:
            strong_signals.append(
                CustomerContact.normalized_email == normalize_email(data.email)
            )
        if data.mobile_phone:
            strong_signals.append(
                CustomerContact.normalized_mobile_phone
                == normalize_phone(data.mobile_phone)
            )
        identity = or_(*strong_signals) if strong_signals else and_(*signals)
        count = await session.scalar(
            select(func.count())
            .select_from(CustomerContact)
            .where(
                CustomerContact.customer_id == customer_id,
                CustomerContact.archived_at.is_(None),
                identity,
            )
        )
        return int(count or 0)

    @staticmethod
    async def _location_match_count(
        session: AsyncSession,
        *,
        customer_id: UUID,
        data: ServiceLocationCreate,
    ) -> int:
        normalized = build_normalized_address(
            data.address,
            data.address_line_2,
            data.city,
            data.state,
            data.postal_code,
        )
        count = await session.scalar(
            select(func.count())
            .select_from(ServiceLocation)
            .where(
                ServiceLocation.customer_id == customer_id,
                ServiceLocation.archived_at.is_(None),
                ServiceLocation.normalized_address == normalized,
            )
        )
        return int(count or 0)

    @staticmethod
    async def _advance(
        session: AsyncSession,
        *,
        run_id: UUID,
        entity_type: EntityType,
        disposition: Disposition,
    ) -> MigrationProgress:
        progress = await session.scalar(
            select(CustomerMigrationProgress)
            .where(
                CustomerMigrationProgress.run_id == run_id,
                CustomerMigrationProgress.entity_type == entity_type,
            )
            .with_for_update()
        )
        run = await session.get(CustomerMigrationRun, run_id, with_for_update=True)
        if progress is None or run is None:
            raise RuntimeError("Migration progress state disappeared")
        progress.processed_count += 1
        if disposition == "accepted":
            progress.accepted_count += 1
        elif disposition == "rejected":
            progress.rejected_count += 1
        elif disposition == "duplicate":
            progress.duplicate_count += 1
        else:
            progress.unresolved_count += 1
        progress.updated_at = utc_now()
        run.source_count += 1
        if disposition == "accepted":
            run.accepted_count += 1
        elif disposition == "rejected":
            run.rejected_count += 1
        elif disposition == "duplicate":
            run.duplicate_count += 1
        else:
            run.unresolved_count += 1
        return MigrationProgress(
            run_id=str(run.id),
            entity_type=entity_type,
            source=progress.source_count,
            processed=progress.processed_count,
            accepted=progress.accepted_count,
            rejected=progress.rejected_count,
            duplicate=progress.duplicate_count,
            unresolved=progress.unresolved_count,
        )

    async def run(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        contacts_path: Path,
        service_locations_path: Path,
        dry_run: bool,
        progress_callback: ProgressCallback | None = None,
    ) -> MigrationReport:
        if context.active_branch is None:
            raise ValueError("An active Branch is required for migration ownership")
        if not context.can_access_branch(context.active_branch.id):
            raise ValueError("The active Branch is outside the authorized branch scope")
        contact_rows = _read_rows(contacts_path, CONTACT_HEADERS)
        location_rows = _read_rows(service_locations_path, LOCATION_HEADERS)
        digest = hashlib.sha256(
            contacts_path.read_bytes() + b"\0" + service_locations_path.read_bytes()
        ).hexdigest()
        async with factory() as session, session.begin():
            run = CustomerMigrationRun(
                company_id=context.company.id,
                branch_id=context.active_branch.id,
                initiated_by_user_id=context.user.id,
                source_system=SOURCE_SYSTEM,
                source_sha256=digest,
                mode="dry_run" if dry_run else "import",
                status="running",
            )
            session.add(run)
            await session.flush()
            run_id = run.id
            session.add_all(
                [
                    CustomerMigrationProgress(
                        run_id=run_id,
                        entity_type="contact",
                        source_count=len(contact_rows),
                        processed_count=0,
                        accepted_count=0,
                        rejected_count=0,
                        duplicate_count=0,
                        unresolved_count=0,
                    ),
                    CustomerMigrationProgress(
                        run_id=run_id,
                        entity_type="service_location",
                        source_count=len(location_rows),
                        processed_count=0,
                        accepted_count=0,
                        rejected_count=0,
                        duplicate_count=0,
                        unresolved_count=0,
                    ),
                ]
            )

        seen: dict[EntityType, set[str]] = {
            "contact": set(),
            "service_location": set(),
        }
        seen_fingerprints: dict[EntityType, set[tuple[str, ...]]] = {
            "contact": set(),
            "service_location": set(),
        }
        try:
            await self._process_contacts(
                factory,
                context=context,
                run_id=run_id,
                rows=contact_rows,
                seen=seen["contact"],
                seen_fingerprints=seen_fingerprints["contact"],
                dry_run=dry_run,
                progress_callback=progress_callback,
            )
            await self._process_locations(
                factory,
                context=context,
                run_id=run_id,
                rows=location_rows,
                seen=seen["service_location"],
                seen_fingerprints=seen_fingerprints["service_location"],
                dry_run=dry_run,
                progress_callback=progress_callback,
            )
        except Exception:
            async with factory() as session, session.begin():
                failed = await session.get(
                    CustomerMigrationRun, run_id, with_for_update=True
                )
                if failed is not None:
                    failed.status = "failed"
                    failed.completed_at = utc_now()
            raise
        async with factory() as session, session.begin():
            completed = await session.get(
                CustomerMigrationRun, run_id, with_for_update=True
            )
            if completed is None:
                raise RuntimeError("Migration run disappeared")
            completed.status = "completed"
            completed.completed_at = utc_now()
            report = MigrationReport(
                run_id=str(completed.id),
                mode=completed.mode,
                source=completed.source_count,
                accepted=completed.accepted_count,
                rejected=completed.rejected_count,
                duplicate=completed.duplicate_count,
                unresolved=completed.unresolved_count,
            )
        return report

    async def _record_nonaccepted(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        run_id: UUID,
        entity_type: EntityType,
        row_number: int,
        source_id: str | None,
        disposition: Literal["rejected", "duplicate", "unresolved"],
        reason: str,
        detail: str,
    ) -> MigrationProgress:
        async with factory() as session, session.begin():
            session.add(
                CustomerMigrationException(
                    run_id=run_id,
                    row_number=row_number,
                    entity_type=entity_type,
                    source_id_sha256=(
                        hashlib.sha256(source_id.encode()).hexdigest()
                        if source_id
                        else None
                    ),
                    disposition=disposition,
                    reason_code=reason,
                    detail=detail,
                )
            )
            return await self._advance(
                session,
                run_id=run_id,
                entity_type=entity_type,
                disposition=disposition,
            )

    async def _process_contacts(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        run_id: UUID,
        rows: list[dict[str, str]],
        seen: set[str],
        seen_fingerprints: set[tuple[str, ...]],
        dry_run: bool,
        progress_callback: ProgressCallback | None,
    ) -> None:
        for row_number, row in enumerate(rows, start=2):
            parsed = None
            disposition: Literal["rejected", "duplicate", "unresolved"] | None = None
            reason = detail = ""
            try:
                parsed = parse_contact(row)
            except UnresolvedRowError as error:
                disposition, reason, detail = (
                    "unresolved",
                    "identity_unresolved",
                    str(error),
                )
            except (ValidationError, ValueError) as error:
                disposition, reason, detail = (
                    "rejected",
                    "validation_failed",
                    str(error),
                )
            source_id = parsed.source_id if parsed else _optional(row, "contact_id")
            fingerprint = None
            if parsed:
                identity: tuple[str, ...]
                if parsed.data.email:
                    identity = ("email", normalize_email(parsed.data.email))
                elif parsed.data.mobile_phone:
                    identity = ("phone", normalize_phone(parsed.data.mobile_phone))
                else:
                    identity = (
                        "name",
                        parsed.data.first_name.lower(),
                        parsed.data.last_name.lower(),
                    )
                fingerprint = (parsed.source_customer_id, *identity)
            if parsed and parsed.source_id in seen:
                disposition, reason, detail = (
                    "duplicate",
                    "duplicate_source_id_in_file",
                    "The source Contact identifier occurs more than once.",
                )
            elif parsed and fingerprint in seen_fingerprints:
                disposition, reason, detail = (
                    "duplicate",
                    "duplicate_identity_in_file",
                    "Another source Contact row has the same normalized identity.",
                )
            elif parsed:
                seen.add(parsed.source_id)
                assert fingerprint is not None
                seen_fingerprints.add(fingerprint)
                async with factory() as session:
                    parent = await self._parent_identity(
                        session,
                        context=context,
                        source_customer_id=parsed.source_customer_id,
                    )
                    existing = await session.scalar(
                        select(CustomerContactSourceIdentity).where(
                            CustomerContactSourceIdentity.company_id
                            == context.company.id,
                            CustomerContactSourceIdentity.source_system
                            == SOURCE_SYSTEM,
                            CustomerContactSourceIdentity.source_contact_id
                            == parsed.source_id,
                        )
                    )
                    matches = (
                        await self._contact_match_count(
                            session, customer_id=parent.customer_id, data=parsed.data
                        )
                        if parent
                        else 0
                    )
                if parent is None:
                    disposition, reason, detail = (
                        "unresolved",
                        "parent_customer_unresolved",
                        "No Customer source identity exists in the active Company and Branch.",
                    )
                elif existing is not None:
                    disposition, reason, detail = (
                        "duplicate",
                        "source_identity_exists",
                        "This source Contact was already migrated.",
                    )
                elif matches:
                    disposition, reason, detail = (
                        "unresolved",
                        "existing_contact_match",
                        f"{matches} existing Contact(s) match; no automatic merge performed.",
                    )
                else:
                    async with factory() as session, session.begin():
                        if not dry_run:
                            contact = (
                                await self.customer_service.stage_migrated_contact(
                                    session,
                                    context=context,
                                    customer_id=parent.customer_id,
                                    data=parsed.data,
                                )
                            )
                            session.add(
                                CustomerContactSourceIdentity(
                                    company_id=context.company.id,
                                    customer_source_identity_id=parent.id,
                                    contact_id=contact.id,
                                    customer_id=parent.customer_id,
                                    source_system=SOURCE_SYSTEM,
                                    source_contact_id=parsed.source_id,
                                    first_run_id=run_id,
                                )
                            )
                        progress = await self._advance(
                            session,
                            run_id=run_id,
                            entity_type="contact",
                            disposition="accepted",
                        )
                    if progress_callback:
                        progress_callback(progress)
                    continue
            assert disposition is not None
            progress = await self._record_nonaccepted(
                factory,
                run_id=run_id,
                entity_type="contact",
                row_number=row_number,
                source_id=source_id,
                disposition=disposition,
                reason=reason,
                detail=detail,
            )
            if progress_callback:
                progress_callback(progress)

    async def _process_locations(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        run_id: UUID,
        rows: list[dict[str, str]],
        seen: set[str],
        seen_fingerprints: set[tuple[str, ...]],
        dry_run: bool,
        progress_callback: ProgressCallback | None,
    ) -> None:
        for row_number, row in enumerate(rows, start=2):
            parsed = None
            disposition: Literal["rejected", "duplicate", "unresolved"] | None = None
            reason = detail = ""
            try:
                parsed = parse_service_location(row)
            except UnresolvedRowError as error:
                disposition, reason, detail = (
                    "unresolved",
                    "identity_unresolved",
                    str(error),
                )
            except (ValidationError, ValueError) as error:
                disposition, reason, detail = (
                    "rejected",
                    "validation_failed",
                    str(error),
                )
            source_id = (
                parsed.source_id if parsed else _optional(row, "service_location_id")
            )
            fingerprint = (
                (
                    parsed.source_customer_id,
                    build_normalized_address(
                        parsed.data.address,
                        parsed.data.address_line_2,
                        parsed.data.city,
                        parsed.data.state,
                        parsed.data.postal_code,
                    ),
                )
                if parsed
                else None
            )
            if parsed and parsed.source_id in seen:
                disposition, reason, detail = (
                    "duplicate",
                    "duplicate_source_id_in_file",
                    "The source Service Location identifier occurs more than once.",
                )
            elif parsed and fingerprint in seen_fingerprints:
                disposition, reason, detail = (
                    "duplicate",
                    "duplicate_identity_in_file",
                    "Another source Service Location row has the same normalized address.",
                )
            elif parsed:
                seen.add(parsed.source_id)
                assert fingerprint is not None
                seen_fingerprints.add(fingerprint)
                async with factory() as session:
                    parent = await self._parent_identity(
                        session,
                        context=context,
                        source_customer_id=parsed.source_customer_id,
                    )
                    existing = await session.scalar(
                        select(ServiceLocationSourceIdentity).where(
                            ServiceLocationSourceIdentity.company_id
                            == context.company.id,
                            ServiceLocationSourceIdentity.source_system
                            == SOURCE_SYSTEM,
                            ServiceLocationSourceIdentity.source_location_id
                            == parsed.source_id,
                        )
                    )
                    matches = (
                        await self._location_match_count(
                            session, customer_id=parent.customer_id, data=parsed.data
                        )
                        if parent
                        else 0
                    )
                if parent is None:
                    disposition, reason, detail = (
                        "unresolved",
                        "parent_customer_unresolved",
                        "No Customer source identity exists in the active Company and Branch.",
                    )
                elif existing is not None:
                    disposition, reason, detail = (
                        "duplicate",
                        "source_identity_exists",
                        "This source Service Location was already migrated.",
                    )
                elif matches:
                    disposition, reason, detail = (
                        "unresolved",
                        "existing_service_location_match",
                        f"{matches} existing Service Location(s) match; no automatic merge performed.",
                    )
                else:
                    async with factory() as session, session.begin():
                        if not dry_run:
                            location = await self.customer_service.stage_migrated_service_location(
                                session,
                                context=context,
                                customer_id=parent.customer_id,
                                data=parsed.data,
                            )
                            session.add(
                                ServiceLocationSourceIdentity(
                                    company_id=context.company.id,
                                    customer_source_identity_id=parent.id,
                                    service_location_id=location.id,
                                    customer_id=parent.customer_id,
                                    source_system=SOURCE_SYSTEM,
                                    source_location_id=parsed.source_id,
                                    first_run_id=run_id,
                                )
                            )
                        progress = await self._advance(
                            session,
                            run_id=run_id,
                            entity_type="service_location",
                            disposition="accepted",
                        )
                    if progress_callback:
                        progress_callback(progress)
                    continue
            assert disposition is not None
            progress = await self._record_nonaccepted(
                factory,
                run_id=run_id,
                entity_type="service_location",
                row_number=row_number,
                source_id=source_id,
                disposition=disposition,
                reason=reason,
                detail=detail,
            )
            if progress_callback:
                progress_callback(progress)

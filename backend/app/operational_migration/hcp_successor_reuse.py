"""Pure contracts for a fail-closed SOURCE.4 successor-aware admission.

The types in this module deliberately perform no database or filesystem writes.  They
turn private reconciliation evidence into a deterministic, scope-bound manifest and
produce the complete dry-run envelope that an executor must verify before mutation.
Raw source/native identifiers remain in the private manifest; the public preflight
contains counts and digests only.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.operational_migration.hcp_successor_reconciliation import (
    LEGACY_SOURCE_SYSTEM,
    SOURCE4_SOURCE_SYSTEM,
    IdentityBinding,
    SealedIdentity,
)

MANIFEST_CONTRACT = "hcp-source4-successor-manifest/v1"
PREFLIGHT_CONTRACT = "hcp-source4-successor-admission-preflight/v1"
AUTHORITATIVE_HYBRID_DIGEST = (
    "228f2e1b1f9050066cd8de5cddfceff6a62461864c0d6a90361040801132cbad"
)
AUTHORITATIVE_CUSTOMER_CONTROL_DIGEST = (
    "c5c81977116c9d4e296a8b4fa763a5029a94752ae00803d9a6c363d7e1ca711e"
)


class AdmissionDisposition(StrEnum):
    REUSE_EXACT_SUCCESSOR = "reuse_exact_successor"
    CREATE_NEW = "create_new"
    HOLD_AMBIGUOUS = "hold_ambiguous"
    CONFLICT = "conflict"


@dataclass(frozen=True, order=True)
class SourceKey:
    domain: str
    source_id: str


@dataclass(frozen=True)
class SuccessorManifestEntry:
    """Private record-level reconciliation evidence."""

    domain: str
    source_id: str
    disposition: AdmissionDisposition
    evidence_digest: str
    native_id: str | None = None
    parent: SourceKey | None = None
    reason: str = ""
    confidence: str = "deterministic"


@dataclass(frozen=True)
class QualifiedSuccessorManifest:
    contract: str
    company_id: str
    branch_id: str
    entries: tuple[SuccessorManifestEntry, ...]
    digest: str

    @classmethod
    def build(
        cls,
        *,
        company_id: str,
        branch_id: str,
        entries: Iterable[SuccessorManifestEntry],
    ) -> QualifiedSuccessorManifest:
        if not company_id or not branch_id:
            raise ValueError("successor manifest scope is required")
        ordered = tuple(sorted(entries, key=_entry_sort_key))
        _validate_entries(ordered)
        payload = _manifest_payload(company_id, branch_id, ordered)
        return cls(
            contract=MANIFEST_CONTRACT,
            company_id=company_id,
            branch_id=branch_id,
            entries=ordered,
            digest=_digest(payload),
        )

    def verify(self) -> None:
        _validate_entries(self.entries)
        if self.contract != MANIFEST_CONTRACT or self.digest != _digest(
            _manifest_payload(self.company_id, self.branch_id, self.entries)
        ):
            raise ValueError("successor manifest digest mismatch")

    def private_payload(self) -> dict[str, object]:
        self.verify()
        return _manifest_payload(self.company_id, self.branch_id, self.entries) | {
            "digest": self.digest
        }

    @classmethod
    def load(cls, path: Path) -> QualifiedSuccessorManifest:
        value: Any = json.loads(path.read_bytes())
        if not isinstance(value, dict) or value.get("contract") != MANIFEST_CONTRACT:
            raise ValueError("successor manifest contract mismatch")
        entries = tuple(
            SuccessorManifestEntry(
                domain=item["domain"],
                source_id=item["source_id"],
                disposition=AdmissionDisposition(item["disposition"]),
                evidence_digest=item["evidence_digest"],
                native_id=item.get("native_id"),
                parent=(SourceKey(**item["parent"]) if item.get("parent") else None),
                reason=item.get("reason", ""),
                confidence=item.get("confidence", "deterministic"),
            )
            for item in value["entries"]
        )
        result = cls(
            contract=value["contract"],
            company_id=value["company_id"],
            branch_id=value["branch_id"],
            entries=entries,
            digest=value["digest"],
        )
        result.verify()
        return result


def build_successor_manifest(
    *,
    company_id: str,
    branch_id: str,
    current_bindings: Iterable[IdentityBinding],
    sealed_source4: Iterable[SealedIdentity],
    parents: dict[SourceKey, SourceKey] | None = None,
) -> QualifiedSuccessorManifest:
    """Classify the sealed population; unrelated legacy Preview rows remain native."""

    by_key: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    target_owners: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for binding in current_bindings:
        by_key[(binding.domain, binding.source_system, binding.source_id)].append(
            binding.target_id
        )
        target_owners[
            (binding.domain, binding.source_system, binding.target_id)
        ].add(binding.source_id)
    entries: list[SuccessorManifestEntry] = []
    for sealed in sorted(sealed_source4, key=lambda item: (item.domain, item.source_id)):
        legacy = by_key.get(
            (sealed.domain, LEGACY_SOURCE_SYSTEM, sealed.source_id), []
        )
        source4 = by_key.get(
            (sealed.domain, SOURCE4_SOURCE_SYSTEM, sealed.source_id), []
        )
        collision = any(
            len(target_owners[(sealed.domain, system, target)]) != 1
            for system, targets in (
                (LEGACY_SOURCE_SYSTEM, legacy),
                (SOURCE4_SOURCE_SYSTEM, source4),
            )
            for target in targets
        )
        if (
            len(legacy) > 1
            or len(source4) > 1
            or collision
            or (source4 and (not legacy or source4[0] != legacy[0]))
        ):
            disposition = AdmissionDisposition.CONFLICT
            native_id = None
            reason = "identity_binding_conflict"
        elif legacy:
            disposition = AdmissionDisposition.REUSE_EXACT_SUCCESSOR
            native_id = legacy[0]
            reason = "unique_legacy_source_identity_match"
        else:
            disposition = AdmissionDisposition.CREATE_NEW
            native_id = None
            reason = "no_existing_source_identity"
        evidence = _digest(
            {
                "domain": sealed.domain,
                "source_id": sealed.source_id,
                "legacy_targets": sorted(legacy),
                "source4_targets": sorted(source4),
                "disposition": disposition.value,
            }
        )
        entries.append(
            SuccessorManifestEntry(
                domain=sealed.domain,
                source_id=sealed.source_id,
                disposition=disposition,
                evidence_digest=evidence,
                native_id=native_id,
                parent=(parents or {}).get(SourceKey(sealed.domain, sealed.source_id)),
                reason=reason,
            )
        )
    return QualifiedSuccessorManifest.build(
        company_id=company_id, branch_id=branch_id, entries=entries
    )


@dataclass(frozen=True)
class AdmissionGuardEvidence:
    hybrid_digest: str
    customer_control_digest: str
    protected_authority: str
    expected_protected_authority: str
    schema_current: str
    schema_head: str
    backup_verified: bool
    authorization_verified: bool
    zero_prior_master_admissions: bool
    zero_migration_drift: bool
    rollback_verified: bool
    security_baseline_verified: bool


@dataclass(frozen=True)
class DomainAdmissionCounts:
    source_total: int
    reuse_exact: int
    create_new: int
    hold: int
    conflict: int


@dataclass(frozen=True)
class SuccessorAdmissionPreflight:
    """Public, identifier-free admission decision envelope."""

    contract: str
    manifest_digest: str
    company_scope_digest: str
    domain_counts: dict[str, DomainAdmissionCounts]
    source_total: int
    existing_preview_overlap_count: int
    duplicate_risk_count: int
    orphan_risk_count: int
    financial_overlap_count: int
    unresolved_owner_decision_count: int
    guard_failures: tuple[str, ...]
    admission_allowed: bool
    digest: str


def qualify_successor_admission(
    manifest: QualifiedSuccessorManifest,
    guards: AdmissionGuardEvidence,
) -> SuccessorAdmissionPreflight:
    """Produce a deterministic dry-run decision without exposing private IDs."""

    manifest.verify()
    keys = {SourceKey(item.domain, item.source_id) for item in manifest.entries}
    blocked = {
        SourceKey(item.domain, item.source_id)
        for item in manifest.entries
        if item.disposition
        in {AdmissionDisposition.HOLD_AMBIGUOUS, AdmissionDisposition.CONFLICT}
    }
    dispositions = {
        SourceKey(item.domain, item.source_id): item.disposition
        for item in manifest.entries
    }
    orphan_count = sum(
        item.parent is not None
        and (
            item.parent not in keys
            or item.parent in blocked
            or (
                item.disposition is AdmissionDisposition.REUSE_EXACT_SUCCESSOR
                and dispositions.get(item.parent) is AdmissionDisposition.CREATE_NEW
            )
        )
        and item.disposition
        in {AdmissionDisposition.REUSE_EXACT_SUCCESSOR, AdmissionDisposition.CREATE_NEW}
        for item in manifest.entries
    )
    reusable_targets = [
        (item.domain, item.native_id)
        for item in manifest.entries
        if item.disposition is AdmissionDisposition.REUSE_EXACT_SUCCESSOR
    ]
    duplicate_count = len(reusable_targets) - len(set(reusable_targets))

    by_domain: dict[str, Counter[AdmissionDisposition]] = defaultdict(Counter)
    for item in manifest.entries:
        by_domain[item.domain][item.disposition] += 1
    counts = {
        domain: DomainAdmissionCounts(
            source_total=sum(values.values()),
            reuse_exact=values[AdmissionDisposition.REUSE_EXACT_SUCCESSOR],
            create_new=values[AdmissionDisposition.CREATE_NEW],
            hold=values[AdmissionDisposition.HOLD_AMBIGUOUS],
            conflict=values[AdmissionDisposition.CONFLICT],
        )
        for domain, values in sorted(by_domain.items())
    }
    failures = _guard_failures(guards)
    conflicts = sum(item.conflict for item in counts.values())
    holds = sum(item.hold for item in counts.values())
    overlap_count = sum(item.reuse_exact for item in counts.values())
    financial_overlap_count = sum(
        counts.get(domain, DomainAdmissionCounts(0, 0, 0, 0, 0)).reuse_exact
        for domain in ("invoice", "payment")
    )
    company_scope_digest = _digest(
        {"company_id": manifest.company_id, "branch_id": manifest.branch_id}
    )
    public = {
        "contract": PREFLIGHT_CONTRACT,
        "manifest_digest": manifest.digest,
        "company_scope_digest": company_scope_digest,
        "domain_counts": counts,
        "source_total": len(manifest.entries),
        "existing_preview_overlap_count": overlap_count,
        "duplicate_risk_count": duplicate_count,
        "orphan_risk_count": orphan_count,
        "financial_overlap_count": financial_overlap_count,
        "unresolved_owner_decision_count": holds + conflicts,
        "guard_failures": failures,
    }
    allowed = not failures and not conflicts and not duplicate_count and not orphan_count
    return SuccessorAdmissionPreflight(
        contract=PREFLIGHT_CONTRACT,
        manifest_digest=manifest.digest,
        company_scope_digest=company_scope_digest,
        domain_counts=counts,
        source_total=len(manifest.entries),
        existing_preview_overlap_count=overlap_count,
        duplicate_risk_count=duplicate_count,
        orphan_risk_count=orphan_count,
        financial_overlap_count=financial_overlap_count,
        unresolved_owner_decision_count=holds + conflicts,
        guard_failures=failures,
        admission_allowed=allowed,
        digest=_digest(
            {
                **public,
                "domain_counts": {
                    key: asdict(value) for key, value in counts.items()
                },
                "admission_allowed": allowed,
            }
        ),
    )


async def qualify_reuse_graph(
    session: AsyncSession,
    *,
    company_id: str,
    branch_id: str,
    plan: Any,
    manifest: QualifiedSuccessorManifest,
) -> None:
    """Validate every reused native row and parent before checkpointed writes."""

    from app.customers.models import Customer, CustomerContact, ServiceLocation
    from app.financials.models import (
        Estimate,
        EstimateLineItem,
        Invoice,
        InvoiceLineItem,
        Payment,
    )
    from app.jobs.models import Job
    from app.scheduling.models import Appointment

    manifest.verify()
    if manifest.company_id != company_id or manifest.branch_id != branch_id:
        raise ValueError("successor manifest scope mismatch")
    targets = {
        SourceKey(item.domain, item.source_id): item.native_id
        for item in manifest.entries
        if item.disposition is AdmissionDisposition.REUSE_EXACT_SUCCESSOR
    }

    async def objects(model: Any, domain: str) -> dict[str, Any]:
        ids = [native for key, native in targets.items() if key.domain == domain]
        if not ids:
            return {}
        rows = (
            await session.scalars(
                select(model).where(model.id.in_([UUID(value) for value in ids]))
            )
        ).all()
        return {str(row.id): row for row in rows}

    customers = await objects(Customer, "customer")
    locations = await objects(ServiceLocation, "service_location")
    jobs = await objects(Job, "job")
    appointments = await objects(Appointment, "appointment")
    estimates = await objects(Estimate, "estimate")
    invoices = await objects(Invoice, "invoice")
    payments = await objects(Payment, "payment")
    aggregate_by_source = {
        item.source_identity: item for item in plan.customers.reviewed.aggregates
    }
    contact_ids = [row.primary_contact_id for row in customers.values() if row.primary_contact_id]
    contacts = {
        str(row.id): row
        for row in (
            await session.scalars(select(CustomerContact).where(CustomerContact.id.in_(contact_ids)))
        ).all()
    }
    for source_id, aggregate in aggregate_by_source.items():
        native_id = targets.get(SourceKey("customer", source_id))
        if native_id is None:
            continue
        customer = customers.get(native_id)
        proposed = aggregate.customer
        if (
            customer is None
            or str(customer.company_id) != company_id
            or str(customer.branch_id) != branch_id
            or customer.display_name != proposed.display_name
            or customer.legal_name != proposed.legal_name
            or customer.customer_type != proposed.customer_type.value
        ):
            raise ValueError("successor Customer drift")
        if aggregate.contact is not None:
            contact = contacts.get(str(customer.primary_contact_id))
            manifest_contact_id = targets.get(SourceKey("contact", source_id))
            if (
                contact is None
                or manifest_contact_id != str(contact.id)
                or contact.customer_id != customer.id
                or contact.first_name != aggregate.contact.first_name
                or contact.last_name != aggregate.contact.last_name
                or contact.normalized_email != aggregate.contact.email
            ):
                raise ValueError("successor Contact drift")
        for location_source, proposed_location in zip(
            aggregate.service_location_source_identities,
            aggregate.service_locations,
            strict=True,
        ):
            location_id = targets.get(SourceKey("service_location", location_source))
            if location_id is None:
                continue
            location = locations.get(location_id)
            if (
                location is None
                or location.customer_id != customer.id
                or str(location.company_id) != company_id
                or str(location.branch_id) != branch_id
                or any(
                    getattr(location, field) != getattr(proposed_location, field)
                    for field in (
                        "address",
                        "address_line_2",
                        "city",
                        "state",
                        "postal_code",
                        "country",
                    )
                )
            ):
                raise ValueError("successor Service Location drift")

    def parent_id(domain: str, source_id: str) -> str | None:
        return targets.get(SourceKey(domain, source_id))

    for record in plan.jobs:
        native_id = parent_id("job", record.source_id)
        if native_id is None:
            continue
        job = jobs.get(native_id)
        if (
            job is None
            or str(job.company_id) != company_id
            or str(job.branch_id) != branch_id
            or str(job.customer_id) != parent_id("customer", record.source_customer_id)
            or str(job.service_location_id)
            != parent_id("service_location", record.source_service_location_id)
            or job.status != record.status
            or job.priority != record.priority
            or job.customer_reported_problem != record.summary
            or job.internal_description != record.description
        ):
            raise ValueError("successor Job drift")
    for record in plan.appointments:
        native_id = parent_id("appointment", record.source_id)
        if native_id is None:
            continue
        appointment = appointments.get(native_id)
        job_id = parent_id("job", record.source_job_id)
        job = jobs.get(job_id or "")
        if (
            appointment is None
            or job is None
            or str(appointment.company_id) != company_id
            or str(appointment.branch_id) != branch_id
            or appointment.customer_id != job.customer_id
            or appointment.service_location_id != job.service_location_id
            or appointment.status != record.status
            or appointment.arrival_window_start_at != record.arrival_window_start_at
            or appointment.arrival_window_end_at != record.arrival_window_end_at
            or appointment.expected_duration_minutes != record.duration_minutes
        ):
            raise ValueError("successor Appointment drift")

    for domain, records, rows, line_model in (
        ("estimate", plan.estimates, estimates, EstimateLineItem),
        ("invoice", plan.invoices, invoices, InvoiceLineItem),
    ):
        for record in records:
            native_id = parent_id(domain, record.source_id)
            if native_id is None:
                continue
            row = rows.get(native_id)
            if (
                row is None
                or str(row.company_id) != company_id
                or str(row.branch_id) != branch_id
                or str(row.job_id) != parent_id("job", record.source_job_id)
                or row.status != record.status
                or row.currency != record.currency
                or row.subtotal_amount != record.subtotal_amount
                or row.tax_amount != record.tax_amount
                or row.total_amount != record.total_amount
            ):
                raise ValueError(f"successor {domain} drift")
            line_items = (
                await session.scalars(
                    select(line_model)
                    .where(getattr(line_model, f"{domain}_id") == row.id)
                    .order_by(line_model.position)
                )
            ).all()
            if len(line_items) != len(record.line_items) or any(
                _financial_line_values(item)
                != (source.quantity, source.unit_price, source.total_amount)
                for item, source in zip(line_items, record.line_items, strict=True)
            ):
                raise ValueError(f"successor {domain} line-item drift")
    for record in plan.payments:
        native_id = parent_id("payment", record.source_id)
        if native_id is None:
            continue
        payment = payments.get(native_id)
        invoice_id = parent_id("invoice", record.source_invoice_id)
        if (
            payment is None
            or str(payment.company_id) != company_id
            or str(payment.branch_id) != branch_id
            or str(payment.invoice_id) != invoice_id
            or payment.status != record.status
            or payment.currency != record.currency
            or payment.amount != record.amount
            or payment.paid_at != record.paid_at
        ):
            raise ValueError("successor Payment drift")


def _entry_sort_key(item: SuccessorManifestEntry) -> tuple[str, str, str]:
    return item.domain, item.source_id, item.disposition.value


def _validate_entries(entries: tuple[SuccessorManifestEntry, ...]) -> None:
    keys: set[SourceKey] = set()
    for item in entries:
        key = SourceKey(item.domain, item.source_id)
        if not item.domain or not item.source_id or key in keys:
            raise ValueError("successor manifest contains missing or duplicate identity")
        keys.add(key)
        if len(item.evidence_digest) != 64:
            raise ValueError("successor manifest evidence digest is invalid")
        try:
            int(item.evidence_digest, 16)
        except ValueError as error:
            raise ValueError("successor manifest evidence digest is invalid") from error
        if (
            item.disposition is AdmissionDisposition.REUSE_EXACT_SUCCESSOR
        ) != bool(item.native_id):
            raise ValueError("only exact reuse entries must bind a native identity")


def _manifest_payload(
    company_id: str,
    branch_id: str,
    entries: tuple[SuccessorManifestEntry, ...],
) -> dict[str, object]:
    return {
        "contract": MANIFEST_CONTRACT,
        "company_id": company_id,
        "branch_id": branch_id,
        "entries": [asdict(item) for item in entries],
    }


def _guard_failures(guards: AdmissionGuardEvidence) -> tuple[str, ...]:
    checks = {
        "hybrid_authority": guards.hybrid_digest == AUTHORITATIVE_HYBRID_DIGEST,
        "customer_control": (
            guards.customer_control_digest
            == AUTHORITATIVE_CUSTOMER_CONTROL_DIGEST
        ),
        "protected_authority": (
            guards.protected_authority == guards.expected_protected_authority
        ),
        "single_current_schema_head": guards.schema_current == guards.schema_head,
        "backup": guards.backup_verified,
        "authorization": guards.authorization_verified,
        "zero_prior_master_admissions": guards.zero_prior_master_admissions,
        "zero_migration_drift": guards.zero_migration_drift,
        "rollback": guards.rollback_verified,
        "security_baseline": guards.security_baseline_verified,
    }
    return tuple(name for name, passed in checks.items() if not passed)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _financial_line_values(item: Any) -> tuple[Any, Any, Any]:
    return item.quantity, item.unit_price, item.total_amount

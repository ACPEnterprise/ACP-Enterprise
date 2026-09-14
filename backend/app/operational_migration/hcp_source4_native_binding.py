"""Exact legacy-to-SOURCE.4 native identity binding for overlay UPDATEs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.models import (
    CustomerSourceIdentity,
    ServiceLocationSourceIdentity,
)
from app.customers.models import Customer, ServiceLocation
from app.jobs.models import Job
from app.operational_migration.hcp_current_overlay import OverlayKey, OverlayRecord
from app.operational_migration.hcp_migration2b import canonical_sha256
from app.operational_migration.models import (
    AppointmentSourceIdentity,
    HcpSource4NativeBindingEvidence,
    JobSourceIdentity,
)
from app.scheduling.models import Appointment

LEGACY_SOURCE = "housecall_pro"
SOURCE4_SOURCE = "housecall_pro_source4"
BINDING_CONTRACT = "hcp-source4-native-successor-binding/v1"


class BindingDisposition(StrEnum):
    BINDING_ALREADY_PRESENT = "BINDING_ALREADY_PRESENT"
    PROVABLE_NATIVE_SUCCESSOR_BINDING = "PROVABLE_NATIVE_SUCCESSOR_BINDING"
    AMBIGUOUS_NATIVE_SUCCESSOR = "AMBIGUOUS_NATIVE_SUCCESSOR"
    CONFLICTING_BINDING = "CONFLICTING_BINDING"
    NATIVE_SUCCESSOR_MISSING = "NATIVE_SUCCESSOR_MISSING"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class NativeBindingCandidate:
    key: OverlayKey
    disposition: BindingDisposition
    native_id: UUID | None
    legacy_identity_id: UUID | None
    predecessor_source_digest: str
    reason: str

    @property
    def digest(self) -> str:
        return canonical_sha256(
            {
                "contract": BINDING_CONTRACT,
                "domain": self.key.domain,
                "source_id": self.key.source_id,
                "disposition": self.disposition.value,
                "native_id": str(self.native_id) if self.native_id else None,
                "legacy_identity_id": (
                    str(self.legacy_identity_id) if self.legacy_identity_id else None
                ),
                "predecessor_source_digest": self.predecessor_source_digest,
                "reason": self.reason,
            }
        )


class HcpSource4NativeBindingBootstrap:
    """Inventory every UPDATE, then materialize only exact legacy successors."""

    def __init__(
        self,
        *,
        company_id: UUID,
        branch_id: UUID,
        master_run_id: UUID,
        customer_run_id: UUID,
        operational_run_id: UUID,
        package_digest: str,
    ) -> None:
        self.company_id = company_id
        self.branch_id = branch_id
        self.master_run_id = master_run_id
        self.customer_run_id = customer_run_id
        self.operational_run_id = operational_run_id
        self.package_digest = package_digest
        self._candidates: dict[OverlayKey, NativeBindingCandidate] = {}

    async def inventory(
        self, session: AsyncSession, records: tuple[OverlayRecord, ...]
    ) -> dict[str, dict[str, int]]:
        updates = tuple(
            record for record in records if record.assertion.value == "update"
        )
        candidates = [await self._classify(session, record) for record in updates]
        self._candidates = {candidate.key: candidate for candidate in candidates}
        blocked = [
            candidate
            for candidate in candidates
            if candidate.disposition
            not in {
                BindingDisposition.BINDING_ALREADY_PRESENT,
                BindingDisposition.PROVABLE_NATIVE_SUCCESSOR_BINDING,
            }
        ]
        if blocked:
            first = min(blocked, key=lambda item: item.key)
            raise ValueError(
                f"overlay UPDATE binding is not mechanically provable: "
                f"{first.key.domain}:{first.key.source_id}:{first.disposition}"
            )
        result: dict[str, dict[str, int]] = {}
        for domain in sorted({candidate.key.domain for candidate in candidates}):
            counts = Counter(
                candidate.disposition.value
                for candidate in candidates
                if candidate.key.domain == domain
            )
            result[domain] = dict(sorted(counts.items()))
        return result

    async def bind_for_update(
        self, session: AsyncSession, record: OverlayRecord
    ) -> None:
        candidate = self._candidates.get(record.key)
        if candidate is None:
            raise ValueError("overlay UPDATE was not included in binding inventory")
        if candidate.disposition is BindingDisposition.BINDING_ALREADY_PRESENT:
            return
        if (
            candidate.disposition
            is not BindingDisposition.PROVABLE_NATIVE_SUCCESSOR_BINDING
        ):
            raise ValueError("overlay UPDATE successor binding is not admissible")
        identity = await self._create_identity(session, record, candidate)
        await self._record_evidence(
            session,
            domain=record.domain,
            source_id=record.source_id,
            native_id=_native_id(identity),
            legacy_identity_id=_required(candidate.legacy_identity_id),
            source4_identity_id=identity.id,
            predecessor_source_digest=candidate.predecessor_source_digest,
            binding_digest=candidate.digest,
            reason=candidate.reason,
        )

    async def _record_evidence(
        self,
        session: AsyncSession,
        *,
        domain: str,
        source_id: str,
        native_id: UUID,
        legacy_identity_id: UUID,
        source4_identity_id: UUID,
        predecessor_source_digest: str,
        binding_digest: str,
        reason: str,
    ) -> None:
        evidence = HcpSource4NativeBindingEvidence(
            company_id=self.company_id,
            branch_id=self.branch_id,
            master_run_id=self.master_run_id,
            domain=domain,
            source4_source_id=source_id,
            native_id=native_id,
            legacy_source_identity_id=legacy_identity_id,
            source4_source_identity_id=source4_identity_id,
            package_digest=self.package_digest,
            predecessor_source_digest=predecessor_source_digest,
            binding_digest=binding_digest,
            evidence={
                "contract": BINDING_CONTRACT,
                "reason": reason,
                "legacy_source_system": LEGACY_SOURCE,
                "source4_source_system": SOURCE4_SOURCE,
                "identity_rule": "exact_provider_identity_and_native_target",
            },
        )
        session.add(evidence)
        await session.flush()

    async def _classify(
        self, session: AsyncSession, record: OverlayRecord
    ) -> NativeBindingCandidate:
        if record.domain not in {"customer", "service_location", "job", "appointment"}:
            return self._candidate(
                record,
                BindingDisposition.UNSUPPORTED,
                None,
                None,
                "unsupported UPDATE domain",
            )
        source4 = await self._identity(session, record.key, SOURCE4_SOURCE)
        legacy = await self._identity(session, record.key, LEGACY_SOURCE)
        if source4 is not None:
            if legacy is not None and _native_id(source4) != _native_id(legacy):
                return self._candidate(
                    record,
                    BindingDisposition.CONFLICTING_BINDING,
                    _native_id(source4),
                    legacy.id,
                    "SOURCE.4 and exact legacy identities target different native records",
                )
            if await self._native_exists(session, record.domain, _native_id(source4)):
                return self._candidate(
                    record,
                    BindingDisposition.BINDING_ALREADY_PRESENT,
                    _native_id(source4),
                    None,
                    "existing exact SOURCE.4 binding",
                )
            return self._candidate(
                record,
                BindingDisposition.CONFLICTING_BINDING,
                _native_id(source4),
                None,
                "SOURCE.4 binding target is missing",
            )
        if legacy is None:
            return self._candidate(
                record,
                BindingDisposition.NATIVE_SUCCESSOR_MISSING,
                None,
                None,
                "exact legacy provider identity is absent",
            )
        native_id = _native_id(legacy)
        if not await self._native_exists(session, record.domain, native_id):
            return self._candidate(
                record,
                BindingDisposition.NATIVE_SUCCESSOR_MISSING,
                native_id,
                legacy.id,
                "legacy native target is absent",
            )
        conflict = await self._target_identity(
            session, record.domain, SOURCE4_SOURCE, native_id
        )
        if conflict is not None:
            return self._candidate(
                record,
                BindingDisposition.CONFLICTING_BINDING,
                native_id,
                legacy.id,
                "native target has a different SOURCE.4 identity",
            )
        if not await self._graph_matches(session, record.domain, legacy):
            return self._candidate(
                record,
                BindingDisposition.CONFLICTING_BINDING,
                native_id,
                legacy.id,
                "legacy identity parent graph conflicts with native graph",
            )
        return self._candidate(
            record,
            BindingDisposition.PROVABLE_NATIVE_SUCCESSOR_BINDING,
            native_id,
            legacy.id,
            "exact legacy provider identity and native parent graph",
        )

    def _candidate(
        self,
        record: OverlayRecord,
        disposition: BindingDisposition,
        native_id: UUID | None,
        legacy_id: UUID | None,
        reason: str,
    ) -> NativeBindingCandidate:
        return NativeBindingCandidate(
            record.key,
            disposition,
            native_id,
            legacy_id,
            record.prior_source_digest or record.source_digest,
            reason,
        )

    async def _identity(
        self, session: AsyncSession, key: OverlayKey, source: str
    ) -> Any:
        model, field = _model_and_source_field(key.domain)
        return await session.scalar(
            select(model).where(
                model.company_id == self.company_id,
                model.branch_id == self.branch_id,
                model.source_system == source,
                field == key.source_id,
            )
        )

    async def _target_identity(
        self, session: AsyncSession, domain: str, source: str, native_id: UUID
    ) -> Any:
        model, _ = _model_and_source_field(domain)
        target = _target_field(model)
        return await session.scalar(
            select(model).where(
                model.company_id == self.company_id,
                model.source_system == source,
                target == native_id,
            )
        )

    async def _native_exists(
        self, session: AsyncSession, domain: str, native_id: UUID
    ) -> bool:
        model = {
            "customer": Customer,
            "service_location": ServiceLocation,
            "job": Job,
            "appointment": Appointment,
        }[domain]
        native: Any = await session.get(model, native_id)
        return (
            native is not None
            and native.company_id == self.company_id
            and (domain == "customer" or native.branch_id == self.branch_id)
        )

    async def _graph_matches(
        self, session: AsyncSession, domain: str, identity: Any
    ) -> bool:
        native: Any = await session.get(
            {
                "customer": Customer,
                "service_location": ServiceLocation,
                "job": Job,
                "appointment": Appointment,
            }[domain],
            _native_id(identity),
        )
        if native is None:
            return False
        if domain == "service_location":
            return native.customer_id == identity.customer_id
        if domain == "job":
            return (
                native.customer_id == identity.customer_id
                and native.service_location_id == identity.service_location_id
            )
        if domain == "appointment":
            return (
                native.job_id == identity.job_id
                and native.customer_id == identity.customer_id
                and native.service_location_id == identity.service_location_id
            )
        return True

    async def _create_identity(
        self,
        session: AsyncSession,
        record: OverlayRecord,
        candidate: NativeBindingCandidate,
    ) -> Any:
        legacy = await self._identity(session, record.key, LEGACY_SOURCE)
        if legacy is None or legacy.id != candidate.legacy_identity_id:
            raise ValueError("legacy successor identity changed after preflight")
        if record.domain == "customer":
            identity: Any = CustomerSourceIdentity(
                company_id=self.company_id,
                branch_id=self.branch_id,
                customer_id=legacy.customer_id,
                source_system=SOURCE4_SOURCE,
                source_customer_id=record.source_id,
                first_run_id=self.customer_run_id,
            )
        elif record.domain == "service_location":
            parent = await self._source4_customer_for_target(
                session, legacy.customer_id
            )
            identity = ServiceLocationSourceIdentity(
                company_id=self.company_id,
                branch_id=self.branch_id,
                master_run_id=self.master_run_id,
                customer_source_identity_id=parent.id,
                service_location_id=legacy.service_location_id,
                customer_id=legacy.customer_id,
                source_system=SOURCE4_SOURCE,
                source_location_id=record.source_id,
                source_digest=candidate.predecessor_source_digest,
                package_digest=self.package_digest,
                transformation_version=BINDING_CONTRACT,
                transformation_digest=candidate.digest,
                source_context={"legacy_source_identity_id": str(legacy.id)},
                first_run_id=self.customer_run_id,
            )
        elif record.domain == "job":
            customer = await self._source4_customer_for_target(
                session, legacy.customer_id
            )
            location = await self._source4_location_for_target(
                session, legacy.service_location_id
            )
            identity = JobSourceIdentity(
                company_id=self.company_id,
                branch_id=self.branch_id,
                job_id=legacy.job_id,
                customer_id=legacy.customer_id,
                service_location_id=legacy.service_location_id,
                customer_source_identity_id=customer.id,
                service_location_source_identity_id=location.id,
                source_system=SOURCE4_SOURCE,
                source_job_id=record.source_id,
                source_job_number=legacy.source_job_number,
                source_status=legacy.source_status,
                assigned_technician_source_ids=list(
                    legacy.assigned_technician_source_ids
                ),
                external_metadata={
                    "successor_binding_digest": candidate.digest,
                    "legacy_source_identity_id": str(legacy.id),
                },
                first_run_id=self.operational_run_id,
            )
        else:
            job = await self._source4_job_for_target(session, legacy.job_id)
            identity = AppointmentSourceIdentity(
                company_id=self.company_id,
                branch_id=self.branch_id,
                appointment_id=legacy.appointment_id,
                job_source_identity_id=job.id,
                job_id=legacy.job_id,
                customer_id=legacy.customer_id,
                service_location_id=legacy.service_location_id,
                source_system=SOURCE4_SOURCE,
                source_appointment_id=record.source_id,
                source_status=legacy.source_status,
                assigned_technician_source_ids=list(
                    legacy.assigned_technician_source_ids
                ),
                external_metadata={
                    "successor_binding_digest": candidate.digest,
                    "legacy_source_identity_id": str(legacy.id),
                },
                first_run_id=self.operational_run_id,
            )
        session.add(identity)
        await session.flush()
        return identity

    async def _source4_customer_for_target(
        self, session: AsyncSession, target: UUID
    ) -> CustomerSourceIdentity:
        value = await self._target_identity(session, "customer", SOURCE4_SOURCE, target)
        if value is None:
            legacy = await self._target_identity(
                session, "customer", LEGACY_SOURCE, target
            )
            if legacy is None:
                raise ValueError("exact legacy Customer parent binding is missing")
            digest = _supporting_digest(
                "customer",
                legacy.source_customer_id,
                target,
                legacy.id,
                self.package_digest,
            )
            value = CustomerSourceIdentity(
                company_id=self.company_id,
                branch_id=self.branch_id,
                customer_id=target,
                source_system=SOURCE4_SOURCE,
                source_customer_id=legacy.source_customer_id,
                first_run_id=self.customer_run_id,
            )
            session.add(value)
            await session.flush()
            await self._record_evidence(
                session,
                domain="customer",
                source_id=legacy.source_customer_id,
                native_id=target,
                legacy_identity_id=legacy.id,
                source4_identity_id=value.id,
                predecessor_source_digest=digest,
                binding_digest=digest,
                reason="exact supporting legacy Customer parent",
            )
        return value

    async def _source4_location_for_target(
        self, session: AsyncSession, target: UUID
    ) -> ServiceLocationSourceIdentity:
        value = await self._target_identity(
            session, "service_location", SOURCE4_SOURCE, target
        )
        if value is None:
            legacy = await self._target_identity(
                session, "service_location", LEGACY_SOURCE, target
            )
            if legacy is None:
                raise ValueError("exact legacy Location parent binding is missing")
            customer = await self._source4_customer_for_target(
                session, legacy.customer_id
            )
            digest = _supporting_digest(
                "service_location",
                legacy.source_location_id,
                target,
                legacy.id,
                self.package_digest,
            )
            value = ServiceLocationSourceIdentity(
                company_id=self.company_id,
                branch_id=self.branch_id,
                master_run_id=self.master_run_id,
                customer_source_identity_id=customer.id,
                service_location_id=target,
                customer_id=legacy.customer_id,
                source_system=SOURCE4_SOURCE,
                source_location_id=legacy.source_location_id,
                source_digest=legacy.source_digest or digest,
                package_digest=self.package_digest,
                transformation_version=BINDING_CONTRACT,
                transformation_digest=digest,
                source_context={
                    "legacy_source_identity_id": str(legacy.id),
                    "supporting_parent": True,
                },
                first_run_id=self.customer_run_id,
            )
            session.add(value)
            await session.flush()
            await self._record_evidence(
                session,
                domain="service_location",
                source_id=legacy.source_location_id,
                native_id=target,
                legacy_identity_id=legacy.id,
                source4_identity_id=value.id,
                predecessor_source_digest=legacy.source_digest or digest,
                binding_digest=digest,
                reason="exact supporting legacy Location parent",
            )
        return value

    async def _source4_job_for_target(
        self, session: AsyncSession, target: UUID
    ) -> JobSourceIdentity:
        value = await self._target_identity(session, "job", SOURCE4_SOURCE, target)
        if value is None:
            legacy = await self._target_identity(session, "job", LEGACY_SOURCE, target)
            if legacy is None:
                raise ValueError("exact legacy Job parent binding is missing")
            customer = await self._source4_customer_for_target(
                session, legacy.customer_id
            )
            location = await self._source4_location_for_target(
                session, legacy.service_location_id
            )
            digest = _supporting_digest(
                "job", legacy.source_job_id, target, legacy.id, self.package_digest
            )
            value = JobSourceIdentity(
                company_id=self.company_id,
                branch_id=self.branch_id,
                job_id=target,
                customer_id=legacy.customer_id,
                service_location_id=legacy.service_location_id,
                customer_source_identity_id=customer.id,
                service_location_source_identity_id=location.id,
                source_system=SOURCE4_SOURCE,
                source_job_id=legacy.source_job_id,
                source_job_number=legacy.source_job_number,
                source_status=legacy.source_status,
                assigned_technician_source_ids=list(
                    legacy.assigned_technician_source_ids
                ),
                external_metadata={
                    "successor_binding_digest": digest,
                    "legacy_source_identity_id": str(legacy.id),
                    "supporting_parent": True,
                },
                first_run_id=self.operational_run_id,
            )
            session.add(value)
            await session.flush()
            await self._record_evidence(
                session,
                domain="job",
                source_id=legacy.source_job_id,
                native_id=target,
                legacy_identity_id=legacy.id,
                source4_identity_id=value.id,
                predecessor_source_digest=digest,
                binding_digest=digest,
                reason="exact supporting legacy Job parent",
            )
        return value


def _model_and_source_field(domain: str):
    model = {
        "customer": CustomerSourceIdentity,
        "service_location": ServiceLocationSourceIdentity,
        "job": JobSourceIdentity,
        "appointment": AppointmentSourceIdentity,
    }[domain]
    field = getattr(
        model,
        {
            "customer": "source_customer_id",
            "service_location": "source_location_id",
            "job": "source_job_id",
            "appointment": "source_appointment_id",
        }[domain],
    )
    return model, field


def _target_field(model: type[object]):
    for name in ("customer_id", "service_location_id", "job_id", "appointment_id"):
        if hasattr(model, name):
            return getattr(model, name)
    raise TypeError("identity model has no native target")


def _native_id(identity: object) -> UUID:
    for name in ("customer_id", "service_location_id", "job_id", "appointment_id"):
        value = getattr(identity, name, None)
        if isinstance(value, UUID):
            return value
    raise TypeError("source identity has no native UUID")


def _required(value: UUID | None) -> UUID:
    if value is None:
        raise ValueError("legacy source identity is required")
    return value


def _supporting_digest(
    domain: str, source_id: str, native_id: UUID, legacy_id: UUID, package_digest: str
) -> str:
    return canonical_sha256(
        {
            "contract": BINDING_CONTRACT,
            "role": "supporting_parent",
            "domain": domain,
            "source_id": source_id,
            "native_id": str(native_id),
            "legacy_source_identity_id": str(legacy_id),
            "package_digest": package_digest,
        }
    )

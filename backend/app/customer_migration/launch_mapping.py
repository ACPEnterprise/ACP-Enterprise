"""Immutable MIG.1 launch mapping and synthetic reconciliation contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID, uuid5

MAPPING_CONTRACT_VERSION = "launch-migration-mapping/v1"
MAPPING_NAMESPACE = UUID("922cb61c-08fc-5f7f-ada4-04424225b38d")
AUTHORITATIVE_ENTERPRISE_COMMIT = "06ba0f39b85b0eeda7e5a4d1747bb326bd28668a"
AUTHORITATIVE_ENTERPRISE_ALEMBIC_HEAD = "t5j7f9b1c386"


class EntityDisposition(StrEnum):
    INCLUDED_FROZEN = "included_frozen"
    INCLUDED_UNMAPPED_OPTIONAL_FIELD = "included_unmapped_optional_field"
    EXCLUDED_FROM_V1_BY_OWNER = "excluded_from_v1_by_owner"
    FAIL_CLOSED_REQUIRES_FUTURE_CONTRACT = "fail_closed_requires_future_contract"


class ReconciliationOutcome(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    AMBIGUOUS = "ambiguous"
    CONFLICT = "conflict"
    OWNER_DISPOSITION_REQUIRED = "owner_disposition_required"
    EXCLUDED = "excluded"


@dataclass(frozen=True)
class EntityMappingContract:
    entity: str
    disposition: EntityDisposition
    source_identity: str
    target_identity: str
    parent_owner: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    intentionally_unmapped_optional_fields: tuple[str, ...]
    transformation_versions: tuple[str, ...]
    lifecycle_mapping: tuple[tuple[str, str], ...]
    reject_taxonomy: tuple[str, ...]
    owner_disposition_requirement: str
    reconciliation_evidence: tuple[str, ...]
    replay_identity: str
    company_branch_ownership: str
    immutable_evidence_requirements: tuple[str, ...]


@dataclass(frozen=True)
class LaunchMappingRegistry:
    contract_version: str
    enterprise_commit: str
    enterprise_alembic_head: str
    mappings: tuple[EntityMappingContract, ...]
    evidence_digest: str

    def mapping(self, entity: str) -> EntityMappingContract:
        for item in self.mappings:
            if item.entity == entity:
                return item
        raise KeyError(entity)


@dataclass(frozen=True)
class SyntheticMappingObservation:
    company_id: UUID
    branch_id: UUID
    entity: str
    provider: str
    source_identity: str | None
    fields: tuple[tuple[str, object], ...]
    parent_identity: str | None = None
    parent_resolved: bool = True
    duplicate_identity: bool = False
    ambiguous_identity: bool = False
    conflicting_evidence: bool = False
    owner_disposition_required: bool = False
    owner_disposition_evidence_sha256: str | None = None


@dataclass(frozen=True)
class MappingReconciliationResult:
    reconciliation_id: UUID
    entity: str
    outcome: ReconciliationOutcome
    reason_code: str | None
    mapped_fields: tuple[tuple[str, object], ...]
    input_digest: str
    evidence_digest: str


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _mapping(
    entity: str,
    disposition: EntityDisposition,
    source_identity: str,
    target_identity: str,
    parent_owner: str,
    required: tuple[str, ...],
    optional: tuple[str, ...],
    *,
    unmapped: tuple[str, ...] = (),
    transforms: tuple[str, ...] = (),
    lifecycle: tuple[tuple[str, str], ...] = (),
    rejects: tuple[str, ...] = (),
    owner_disposition: str = "required_for_any_unresolved_or_conflicting_evidence",
    reconciliation: tuple[str, ...] = (
        "source_identity",
        "parent_identity",
        "company_branch_scope",
        "evidence_digest",
    ),
) -> EntityMappingContract:
    return EntityMappingContract(
        entity=entity,
        disposition=disposition,
        source_identity=source_identity,
        target_identity=target_identity,
        parent_owner=parent_owner,
        required_fields=required,
        optional_fields=optional,
        intentionally_unmapped_optional_fields=unmapped,
        transformation_versions=transforms,
        lifecycle_mapping=lifecycle,
        reject_taxonomy=rejects,
        owner_disposition_requirement=owner_disposition,
        reconciliation_evidence=reconciliation,
        replay_identity="provider+entity+company+branch+source_identity+input_digest",
        company_branch_ownership="exact_company_and_branch_scope_required",
        immutable_evidence_requirements=(
            "source_artifact_sha256",
            "source_record_sha256",
            "transformation_version",
            "reconciliation_digest",
        ),
    )


def build_v1_registry() -> LaunchMappingRegistry:
    """Build the canonical owner-approved V1 registry without runtime data."""
    excluded = EntityDisposition.EXCLUDED_FROM_V1_BY_OWNER
    unmapped = EntityDisposition.INCLUDED_UNMAPPED_OPTIONAL_FIELD
    frozen = EntityDisposition.INCLUDED_FROZEN
    common_rejects = (
        "missing_source_identity",
        "duplicate_source_identity",
        "ambiguous_identity",
        "conflicting_evidence",
        "missing_parent",
        "company_branch_scope_conflict",
        "domain_validation_failed",
    )
    mappings = (
        _mapping(
            "customer",
            unmapped,
            "provider_customer_id",
            "CustomerSourceIdentity.customer_id",
            "crm",
            ("customer_type", "display_name"),
            (
                "legal_name",
                "preferred_contact_method",
                "marketing_source",
                "tax_exempt",
                "notes",
                "status",
            ),
            unmapped=(
                "first_name",
                "last_name",
                "business_name",
                "primary_phone",
                "secondary_phone",
                "email",
                "is_vip",
            ),
            transforms=(
                "customer-adapter-review/v1",
                "native-customer-identity-consolidation/v1",
            ),
            lifecycle=(
                ("prospect", "prospect"),
                ("active", "active"),
                ("inactive", "inactive"),
            ),
            rejects=common_rejects
            + ("unsupported_customer_export_schema", "customer_name_unresolved"),
        ),
        _mapping(
            "contact",
            unmapped,
            "customer_scoped_contact_source_id",
            "CustomerContactSourceIdentity.contact_id",
            "crm.customer",
            ("first_name", "last_name"),
            (
                "title",
                "email",
                "mobile_phone",
                "office_phone",
                "is_preferred",
                "active",
                "notes",
            ),
            unmapped=("relationship_or_role", "can_approve_work"),
            transforms=("customer-adapter-review/v1",),
            rejects=common_rejects + ("contact_name_unresolved",),
        ),
        _mapping(
            "service_location",
            unmapped,
            "provider_scoped_native_service_location_id_sha256",
            "ServiceLocationSourceIdentity.service_location_id",
            "crm.customer",
            ("source_customer_id", "address", "city", "state", "postal_code"),
            (
                "nickname",
                "address_line_2",
                "country",
                "gps_latitude",
                "gps_longitude",
                "billing_address_override",
                "gate_code",
                "property_notes",
                "active",
            ),
            unmapped=(
                "property_type",
                "gate_access_instructions",
                "water_shutoff_location",
                "sewer_septic",
                "is_primary",
            ),
            transforms=(
                "native-service-location-identity/v1",
                "native-service-location-matching/v1",
            ),
            rejects=common_rejects
            + (
                "missing_source_location_identifier",
                "normalized_address_multiple_source_identifiers",
                "parent_mismatch",
                "address_review_required",
            ),
        ),
        _mapping(
            "job",
            frozen,
            "provider_job_id",
            "JobSourceIdentity.job_id",
            "jobs",
            ("source_customer_id", "source_service_location_id", "status"),
            (
                "source_job_number",
                "activated_at",
                "started_at",
                "completed_at",
                "summary",
                "description",
                "priority",
                "assigned_technician_source_ids",
                "external_metadata",
            ),
            transforms=("operational-phase1-hcp/v1",),
            lifecycle=(
                ("draft", "draft"),
                ("ready", "ready"),
                ("in_progress", "in_progress"),
                ("completed", "completed"),
            ),
            rejects=common_rejects
            + (
                "unsupported_paused_or_cancelled_lifecycle",
                "invalid_lifecycle_timestamps",
            ),
        ),
        _mapping(
            "appointment",
            frozen,
            "provider_appointment_id",
            "AppointmentSourceIdentity.appointment_id",
            "scheduling",
            (
                "source_job_id",
                "source_customer_id",
                "source_service_location_id",
                "status",
            ),
            (
                "arrival_window_start_at",
                "arrival_window_end_at",
                "duration_minutes",
                "assigned_technician_source_ids",
                "notes",
                "external_metadata",
            ),
            transforms=("operational-phase1-hcp/v1",),
            lifecycle=(
                ("draft", "draft"),
                ("scheduled", "scheduled"),
                ("confirmed", "confirmed"),
                ("completed", "completed"),
                ("no_show", "no_show"),
            ),
            rejects=common_rejects
            + (
                "duplicate_parent_arrival_window",
                "parent_mismatch",
                "unsupported_cancelled_lifecycle",
            ),
        ),
        _mapping(
            "estimate",
            excluded,
            "not_defined_in_v1",
            "Enterprise Estimate (reserved)",
            "financials",
            (),
            (),
            transforms=(),
            lifecycle=(),
            rejects=("excluded_by_owner", "future_provider_contract_required"),
            owner_disposition="owner_excluded_from_v1",
        ),
        _mapping(
            "invoice",
            frozen,
            "provider_invoice_id",
            "InvoiceSourceIdentity.invoice_id",
            "financials.job",
            (
                "source_job_id",
                "status",
                "currency",
                "subtotal_amount",
                "tax_amount",
                "total_amount",
                "line_items",
            ),
            ("issued_at", "due_on", "external_metadata"),
            transforms=("operational-phase2-hcp-financial/v1",),
            lifecycle=(("draft", "draft"),),
            rejects=common_rejects
            + (
                "unresolved_invoice",
                "monetary_imbalance",
                "incomplete_financial_detail",
            ),
        ),
        _mapping(
            "payment",
            frozen,
            "provider_payment_id",
            "PaymentSourceIdentity.payment_id",
            "financials.invoice",
            ("source_invoice_id", "status", "currency", "amount"),
            ("paid_at", "method", "reference", "external_metadata"),
            transforms=("operational-phase2-hcp-financial/v1",),
            lifecycle=(("succeeded", "succeeded"),),
            rejects=common_rejects
            + (
                "unresolved_invoice",
                "monetary_imbalance",
                "incomplete_financial_detail",
            ),
        ),
        _mapping(
            "note",
            excluded,
            "not_defined_in_v1",
            "MigrationHistoryEntry (reserved)",
            "future_parent_contract",
            (),
            (),
            rejects=("excluded_by_owner", "future_provider_contract_required"),
            owner_disposition="owner_excluded_from_v1",
        ),
        _mapping(
            "attachment",
            excluded,
            "not_defined_in_v1",
            "MigrationArtifact (reserved)",
            "future_parent_contract",
            (),
            (),
            rejects=("excluded_by_owner", "future_provider_contract_required"),
            owner_disposition="owner_excluded_from_v1",
        ),
    )
    canonical = [
        MAPPING_CONTRACT_VERSION,
        AUTHORITATIVE_ENTERPRISE_COMMIT,
        AUTHORITATIVE_ENTERPRISE_ALEMBIC_HEAD,
        [asdict(item) for item in mappings],
    ]
    return LaunchMappingRegistry(
        MAPPING_CONTRACT_VERSION,
        AUTHORITATIVE_ENTERPRISE_COMMIT,
        AUTHORITATIVE_ENTERPRISE_ALEMBIC_HEAD,
        mappings,
        _digest(canonical),
    )


class LaunchMappingReconciler:
    """Validate synthetic mapping evidence without persistence or domain mutation."""

    def __init__(self, registry: LaunchMappingRegistry) -> None:
        self._registry = registry

    def reconcile(
        self,
        observation: SyntheticMappingObservation,
        *,
        expected_company_id: UUID,
        expected_branch_id: UUID,
    ) -> MappingReconciliationResult:
        mapping = self._registry.mapping(observation.entity)
        fields = dict(observation.fields)
        if len(fields) != len(observation.fields):
            return self._result(
                observation,
                ReconciliationOutcome.CONFLICT,
                "duplicate_field_evidence",
                (),
            )
        if mapping.disposition is EntityDisposition.EXCLUDED_FROM_V1_BY_OWNER:
            return self._result(
                observation, ReconciliationOutcome.EXCLUDED, "excluded_by_owner", ()
            )
        if observation.company_id != expected_company_id:
            return self._result(
                observation,
                ReconciliationOutcome.CONFLICT,
                "company_scope_conflict",
                (),
            )
        if observation.branch_id != expected_branch_id:
            return self._result(
                observation, ReconciliationOutcome.CONFLICT, "branch_scope_conflict", ()
            )
        if not observation.source_identity or not observation.source_identity.strip():
            return self._result(
                observation,
                ReconciliationOutcome.REJECTED,
                "missing_source_identity",
                (),
            )
        if observation.duplicate_identity:
            return self._result(
                observation,
                ReconciliationOutcome.DUPLICATE,
                "duplicate_source_identity",
                (),
            )
        if observation.ambiguous_identity:
            return self._result(
                observation, ReconciliationOutcome.AMBIGUOUS, "ambiguous_identity", ()
            )
        if observation.conflicting_evidence:
            return self._result(
                observation, ReconciliationOutcome.CONFLICT, "conflicting_evidence", ()
            )
        if mapping.parent_owner != "crm" and not observation.parent_resolved:
            return self._result(
                observation, ReconciliationOutcome.REJECTED, "missing_parent", ()
            )
        if observation.owner_disposition_required and not _is_sha256(
            observation.owner_disposition_evidence_sha256
        ):
            return self._result(
                observation,
                ReconciliationOutcome.OWNER_DISPOSITION_REQUIRED,
                "owner_disposition_required",
                (),
            )
        fabricated = set(fields) & set(mapping.intentionally_unmapped_optional_fields)
        if fabricated:
            return self._result(
                observation,
                ReconciliationOutcome.CONFLICT,
                "unmapped_optional_field_present",
                (),
            )
        missing = set(mapping.required_fields) - set(fields)
        if missing:
            return self._result(
                observation,
                ReconciliationOutcome.REJECTED,
                "missing_required_field",
                (),
            )
        lifecycle = dict(mapping.lifecycle_mapping)
        if lifecycle and "status" in fields and fields["status"] not in lifecycle:
            return self._result(
                observation,
                ReconciliationOutcome.REJECTED,
                "unsupported_lifecycle",
                (),
            )
        allowed = set(mapping.required_fields) | set(mapping.optional_fields)
        if set(fields) - allowed:
            return self._result(
                observation, ReconciliationOutcome.REJECTED, "unsupported_field", ()
            )
        mapped = tuple(sorted(fields.items()))
        return self._result(observation, ReconciliationOutcome.ACCEPTED, None, mapped)

    @staticmethod
    def _result(
        observation: SyntheticMappingObservation,
        outcome: ReconciliationOutcome,
        reason: str | None,
        mapped_fields: tuple[tuple[str, object], ...],
    ) -> MappingReconciliationResult:
        input_digest = _digest(observation)
        evidence_digest = _digest(
            [
                MAPPING_CONTRACT_VERSION,
                input_digest,
                outcome.value,
                reason,
                mapped_fields,
            ]
        )
        identity = uuid5(MAPPING_NAMESPACE, evidence_digest)
        return MappingReconciliationResult(
            identity,
            observation.entity,
            outcome,
            reason,
            mapped_fields,
            input_digest,
            evidence_digest,
        )


def _is_sha256(value: str | None) -> bool:
    return (
        value is not None
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


V1_MAPPING_REGISTRY = build_v1_registry()
V1_MAPPINGS = MappingProxyType(
    {item.entity: item for item in V1_MAPPING_REGISTRY.mappings}
)


def preserve_exact_money(value: Decimal) -> Decimal:
    """Return an exact Decimal; conversion, quantization, and inference are forbidden."""
    if not value.is_finite():
        raise ValueError("financial value must be finite")
    return value

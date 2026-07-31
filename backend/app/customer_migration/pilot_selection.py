"""Deterministic, provider-neutral Customer pilot selection manifests."""

import hashlib
import json
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.customer_migration.adapter_import import ReviewedCustomerAdapterOutput
from app.customer_migration.adapter_import_policy import (
    CustomerAdapterImportPolicy,
    customer_adapter_import_policy,
)

PILOT_MANIFEST_VERSION = "customer-pilot-manifest/v1"
SELECTION_VERSION = "eligible-source-identity-sha256/v1"


class PilotEligibilityStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reviewed: int = Field(ge=0)
    eligible: int = Field(ge=0)
    selected: int = Field(ge=1)
    rejected: int = Field(ge=0)
    duplicate: int = Field(ge=0)
    child_exception: int = Field(ge=0)
    multi_location: int = Field(ge=0)


class CustomerPilotManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_version: str
    selection_version: str
    source_system: str
    source_sha256: str
    export_version: str
    transformation_version: str
    migration_version: str
    ordered_source_identities: tuple[str, ...] = Field(min_length=1)
    ordered_customer_identity_sha256: tuple[str, ...] = Field(min_length=1)
    eligibility: PilotEligibilityStatistics
    expected_customers: int = Field(ge=1)
    expected_contacts: int = Field(ge=0)
    expected_service_locations: int = Field(ge=0)
    expected_billing_addresses: int = Field(ge=0)
    expected_business_events: int = Field(ge=0)
    replay_key: str
    generated_at: datetime
    manifest_sha256: str

    def integrity_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"manifest_sha256"})

    @model_validator(mode="after")
    def validate_integrity(self) -> "CustomerPilotManifest":
        if self.manifest_version != PILOT_MANIFEST_VERSION:
            raise ValueError("unsupported pilot manifest version")
        if self.selection_version != SELECTION_VERSION:
            raise ValueError("unsupported pilot selection version")
        if len(self.ordered_source_identities) != len(
            self.ordered_customer_identity_sha256
        ):
            raise ValueError("manifest identity lists do not reconcile")
        if self.expected_customers != len(self.ordered_source_identities):
            raise ValueError("manifest Customer count does not reconcile")
        expected = hashlib.sha256(
            json.dumps(
                self.integrity_payload(), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        if expected != self.manifest_sha256:
            raise ValueError("pilot manifest digest mismatch")
        return self


class CustomerPilotSelectionService:
    def __init__(
        self, policy: CustomerAdapterImportPolicy = customer_adapter_import_policy
    ) -> None:
        self.policy = policy

    def select(
        self,
        reviewed: ReviewedCustomerAdapterOutput,
        *,
        migration_version: str,
        limit: int = 25,
        generated_at: datetime | None = None,
    ) -> CustomerPilotManifest:
        reviewed.validate_integrity()
        if limit < 1:
            raise ValueError("pilot limit must be positive")
        duplicate_members = self.policy.duplicate_members(reviewed.aggregates)
        rejected = set(reviewed.rejected_source_identities)
        duplicates = set(reviewed.duplicate_source_identities) | duplicate_members
        children = set(reviewed.child_exception_source_identities)
        multi = {
            item.source_identity_sha256
            for item in reviewed.aggregates
            if len(item.service_locations) > 1
        }
        blocked = rejected | duplicates | children | multi
        eligible = sorted(
            (
                item
                for item in reviewed.aggregates
                if item.source_identity_sha256 not in blocked
            ),
            key=lambda item: item.source_identity_sha256,
        )
        selected = tuple(eligible[:limit])
        if len(selected) != limit:
            raise ValueError("insufficient eligible Customer aggregates")
        timestamp = generated_at or datetime.now(timezone.utc)
        identities = tuple(item.source_identity for item in selected)
        hashes = tuple(item.source_identity_sha256 for item in selected)
        values: dict[str, object] = {
            "manifest_version": PILOT_MANIFEST_VERSION,
            "selection_version": SELECTION_VERSION,
            "source_system": reviewed.source_system,
            "source_sha256": reviewed.source_sha256,
            "export_version": reviewed.schema_version,
            "transformation_version": reviewed.transformation_sha256,
            "migration_version": migration_version,
            "ordered_source_identities": identities,
            "ordered_customer_identity_sha256": hashes,
            "eligibility": PilotEligibilityStatistics(
                reviewed=len(reviewed.aggregates),
                eligible=len(eligible),
                selected=len(selected),
                rejected=len(rejected),
                duplicate=len(duplicates),
                child_exception=len(children),
                multi_location=len(multi),
            ),
            "expected_customers": len(selected),
            "expected_contacts": sum(item.contact is not None for item in selected),
            "expected_service_locations": sum(
                len(item.service_locations) for item in selected
            ),
            "expected_billing_addresses": sum(
                item.billing_address is not None for item in selected
            ),
            "expected_business_events": sum(
                1
                + (item.contact is not None)
                + len(item.service_locations)
                + (item.billing_address is not None)
                for item in selected
            ),
            "replay_key": hashlib.sha256(
                json.dumps(hashes, separators=(",", ":")).encode()
            ).hexdigest(),
            "generated_at": timestamp,
        }
        provisional = CustomerPilotManifest.model_construct(
            manifest_sha256="", **values  # type: ignore[arg-type]
        )
        payload = json.dumps(
            provisional.integrity_payload(), sort_keys=True, separators=(",", ":")
        )
        return CustomerPilotManifest.model_validate(
            {
                **values,
                "manifest_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            }
        )


customer_pilot_selection_service = CustomerPilotSelectionService()

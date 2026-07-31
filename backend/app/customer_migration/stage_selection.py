"""Deterministic cumulative Customer migration stage manifests."""

import hashlib
import json
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.customer_migration.adapter_import import ReviewedCustomerAdapterOutput
from app.customer_migration.adapter_import_policy import (
    CustomerAdapterImportPolicy,
    customer_adapter_import_policy,
)
from app.customer_migration.pilot_selection import (
    CustomerPilotManifest,
    PilotEligibilityStatistics,
)

STAGE_MANIFEST_VERSION = "customer-migration-stage-manifest/v1"
STAGE_SELECTION_VERSION = "eligible-source-identity-sha256/v1"


class CustomerMigrationStageManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_version: str
    selection_version: str
    stage_identifier: str = Field(min_length=1, max_length=100)
    prior_stage_identifier: str | None = Field(default=None, max_length=100)
    prior_stage_manifest_sha256: str | None = None
    source_system: str
    source_sha256: str
    export_version: str
    transformation_version: str
    transformation_sha256: str
    reviewed_output_sha256: str
    migration_version: str
    ordered_source_identities: tuple[str, ...] = Field(min_length=1)
    ordered_customer_identity_sha256: tuple[str, ...] = Field(min_length=1)
    eligibility: PilotEligibilityStatistics
    expected_customers: int = Field(ge=1)
    expected_contacts: int = Field(ge=0)
    expected_service_locations: int = Field(ge=0)
    expected_billing_addresses: int = Field(ge=0)
    expected_business_events: int = Field(ge=0)
    replay_digest: str
    generated_at: datetime
    manifest_sha256: str

    @property
    def replay_key(self) -> str:
        return self.replay_digest

    def integrity_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"manifest_sha256"})

    @model_validator(mode="after")
    def validate_integrity(self) -> "CustomerMigrationStageManifest":
        if self.manifest_version != STAGE_MANIFEST_VERSION:
            raise ValueError("unsupported Customer migration stage manifest version")
        if self.selection_version != STAGE_SELECTION_VERSION:
            raise ValueError("unsupported Customer migration stage selection version")
        if (self.prior_stage_identifier is None) != (
            self.prior_stage_manifest_sha256 is None
        ):
            raise ValueError(
                "prior-stage identifier and digest must be supplied together"
            )
        if self.transformation_version != self.transformation_sha256:
            raise ValueError("transformation version and checksum do not reconcile")
        if len(self.ordered_source_identities) != len(
            self.ordered_customer_identity_sha256
        ):
            raise ValueError("manifest identity lists do not reconcile")
        if self.expected_customers != len(self.ordered_source_identities):
            raise ValueError("manifest Customer count does not reconcile")
        replay = hashlib.sha256(
            json.dumps(
                self.ordered_customer_identity_sha256, separators=(",", ":")
            ).encode()
        ).hexdigest()
        if replay != self.replay_digest:
            raise ValueError("stage replay digest mismatch")
        expected = hashlib.sha256(
            json.dumps(
                self.integrity_payload(), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        if expected != self.manifest_sha256:
            raise ValueError("stage manifest digest mismatch")
        return self


class CustomerMigrationStageSelectionService:
    def __init__(
        self, policy: CustomerAdapterImportPolicy = customer_adapter_import_policy
    ) -> None:
        self.policy = policy

    def select(
        self,
        reviewed: ReviewedCustomerAdapterOutput,
        *,
        stage_identifier: str,
        migration_version: str,
        limit: int | None,
        prior_stage: CustomerMigrationStageManifest
        | CustomerPilotManifest
        | None = None,
        generated_at: datetime | None = None,
    ) -> CustomerMigrationStageManifest:
        reviewed.validate_integrity()
        if limit is not None and limit < 1:
            raise ValueError("stage limit must be positive")
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
        eligible = tuple(
            sorted(
                (
                    item
                    for item in reviewed.aggregates
                    if item.source_identity_sha256 not in blocked
                ),
                key=lambda item: item.source_identity_sha256,
            )
        )
        selected = eligible if limit is None else eligible[:limit]
        if limit is not None and len(selected) != limit:
            raise ValueError("insufficient eligible Customer aggregates")
        hashes = tuple(item.source_identity_sha256 for item in selected)
        if prior_stage is not None:
            prior_stage.validate_integrity()
            if (
                prior_stage.source_sha256 != reviewed.source_sha256
                or prior_stage.transformation_version != reviewed.transformation_sha256
                or hashes[: prior_stage.expected_customers]
                != prior_stage.ordered_customer_identity_sha256
            ):
                raise ValueError("prior stage is not a cumulative prefix")
        values: dict[str, object] = {
            "manifest_version": STAGE_MANIFEST_VERSION,
            "selection_version": STAGE_SELECTION_VERSION,
            "stage_identifier": stage_identifier,
            "prior_stage_identifier": (
                (
                    prior_stage.stage_identifier
                    if isinstance(prior_stage, CustomerMigrationStageManifest)
                    else "pilot-25"
                )
                if prior_stage is not None
                else None
            ),
            "prior_stage_manifest_sha256": (
                prior_stage.manifest_sha256 if prior_stage is not None else None
            ),
            "source_system": reviewed.source_system,
            "source_sha256": reviewed.source_sha256,
            "export_version": reviewed.schema_version,
            "transformation_version": reviewed.transformation_sha256,
            "transformation_sha256": reviewed.transformation_sha256,
            "reviewed_output_sha256": reviewed.review_sha256,
            "migration_version": migration_version,
            "ordered_source_identities": tuple(
                item.source_identity for item in selected
            ),
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
            "replay_digest": hashlib.sha256(
                json.dumps(hashes, separators=(",", ":")).encode()
            ).hexdigest(),
            "generated_at": generated_at or datetime.now(timezone.utc),
        }
        provisional = CustomerMigrationStageManifest.model_construct(
            manifest_sha256="",
            **values,  # type: ignore[arg-type]
        )
        digest = hashlib.sha256(
            json.dumps(
                provisional.integrity_payload(), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        return CustomerMigrationStageManifest.model_validate(
            {**values, "manifest_sha256": digest}
        )


customer_migration_stage_selection_service = CustomerMigrationStageSelectionService()

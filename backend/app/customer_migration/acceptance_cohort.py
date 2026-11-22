"""Deterministic, non-PII Customer acceptance cohort evidence."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.customer_migration.adapter_import import (
    ReviewedCustomerAggregate,
    review_adapter_output,
)
from app.customer_migration.housecall_pro_adapter import (
    HousecallProCustomerExportAdapter,
)
from app.customer_migration.pilot_selection import (
    SELECTION_VERSION,
    CustomerPilotSelectionService,
)

ACCEPTANCE_COHORT_CONTRACT = "customer-acceptance-cohort/v1"
ADAPTER_NAME = "housecall-pro-customer-export"
MAX_ACCEPTANCE_COHORT = 1_000
MAX_MANDATORY_ANCHORS = 100
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_DETERMINISTIC_SELECTION_TIME = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _require_digest(value: str, label: str) -> None:
    if _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


class AcceptanceCohortIdentity(BaseModel):
    """A provider identity and source-row binding, without Customer PII."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_identity: str = Field(min_length=1, max_length=191)
    source_identity_sha256: str
    source_row_sha256: str

    @model_validator(mode="after")
    def validate_digests(self) -> AcceptanceCohortIdentity:
        _require_digest(self.source_identity_sha256, "source_identity_sha256")
        _require_digest(self.source_row_sha256, "source_row_sha256")
        expected = hashlib.sha256(self.source_identity.encode()).hexdigest()
        if self.source_identity_sha256 != expected:
            raise ValueError("source identity digest mismatch")
        return self


class CustomerAcceptanceCohort(BaseModel):
    """Canonical file-only evidence for an operational acceptance cohort."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str
    adapter: str
    source_system: str
    source_sha256: str
    schema_version: str
    transformation_sha256: str
    review_version: str
    reviewed_output_sha256: str
    selection_version: str
    eligibility_manifest_sha256: str
    migration_release_sha: str
    limit: int = Field(ge=1, le=MAX_ACCEPTANCE_COHORT)
    eligible_count: int = Field(ge=1)
    selected: tuple[AcceptanceCohortIdentity, ...] = Field(min_length=1)
    mandatory_anchors: tuple[AcceptanceCohortIdentity, ...] = Field(min_length=1)
    artifact_sha256: str

    def integrity_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"artifact_sha256"})

    @model_validator(mode="after")
    def validate_integrity(self) -> CustomerAcceptanceCohort:
        if self.contract != ACCEPTANCE_COHORT_CONTRACT:
            raise ValueError("unsupported acceptance cohort contract")
        if self.adapter != ADAPTER_NAME:
            raise ValueError("unsupported acceptance cohort adapter")
        if self.selection_version != SELECTION_VERSION:
            raise ValueError("unsupported acceptance cohort selection version")
        for label, value in (
            ("source_sha256", self.source_sha256),
            ("transformation_sha256", self.transformation_sha256),
            ("reviewed_output_sha256", self.reviewed_output_sha256),
            ("eligibility_manifest_sha256", self.eligibility_manifest_sha256),
            ("artifact_sha256", self.artifact_sha256),
        ):
            _require_digest(value, label)
        if _GIT_SHA.fullmatch(self.migration_release_sha) is None:
            raise ValueError("migration_release_sha must be a lowercase Git SHA")
        if len(self.selected) != self.limit:
            raise ValueError("selected cohort does not reconcile with limit")
        selected_ids = [item.source_identity for item in self.selected]
        anchor_ids = [item.source_identity for item in self.mandatory_anchors]
        if len(selected_ids) != len(set(selected_ids)):
            raise ValueError("selected cohort contains duplicate identities")
        if len(anchor_ids) != len(set(anchor_ids)):
            raise ValueError("mandatory anchors contain duplicate identities")
        if set(selected_ids) & set(anchor_ids):
            raise ValueError("mandatory anchors must be separate from the cohort")
        expected = hashlib.sha256(
            _canonical_json(self.integrity_payload()).encode()
        ).hexdigest()
        if self.artifact_sha256 != expected:
            raise ValueError("acceptance cohort artifact digest mismatch")
        return self


def _identity(item: ReviewedCustomerAggregate) -> AcceptanceCohortIdentity:
    return AcceptanceCohortIdentity(
        source_identity=item.source_identity,
        source_identity_sha256=item.source_identity_sha256,
        source_row_sha256=item.source_row_sha256,
    )


def generate_customer_acceptance_cohort(
    source_bytes: bytes,
    *,
    expected_source_sha256: str,
    migration_release_sha: str,
    mandatory_source_ids: Iterable[str],
    limit: int = 25,
    source_system: str = "housecall_pro",
) -> CustomerAcceptanceCohort:
    """Transform, review, and select a deterministic non-anchor cohort."""

    _require_digest(expected_source_sha256, "expected_source_sha256")
    if _GIT_SHA.fullmatch(migration_release_sha) is None:
        raise ValueError("migration_release_sha must be a lowercase Git SHA")
    if not 1 <= limit <= MAX_ACCEPTANCE_COHORT:
        raise ValueError("acceptance cohort limit is outside the supported bound")
    anchor_ids = tuple(mandatory_source_ids)
    if not anchor_ids or any(not value for value in anchor_ids):
        raise ValueError("at least one non-empty mandatory source ID is required")
    if len(anchor_ids) > MAX_MANDATORY_ANCHORS:
        raise ValueError("mandatory source ID count exceeds the supported bound")
    if len(anchor_ids) != len(set(anchor_ids)):
        raise ValueError("mandatory source IDs must be unique")
    actual_source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if actual_source_sha256 != expected_source_sha256:
        raise ValueError("source checksum mismatch")

    transformed = HousecallProCustomerExportAdapter().transform(
        source_bytes,
        expected_source_sha256=expected_source_sha256,
    )
    if transformed.schema_version is None:
        raise ValueError("source Customer export schema is unsupported")
    reviewed = review_adapter_output(transformed, source_system=source_system)

    by_identity = {item.source_identity: item for item in reviewed.aggregates}
    missing = set(anchor_ids) - set(by_identity)
    if missing:
        raise ValueError("mandatory source ID is absent from reviewed output")

    selection = CustomerPilotSelectionService()
    duplicate_members = selection.policy.duplicate_members(reviewed.aggregates)
    blocked = (
        set(reviewed.rejected_source_identities)
        | set(reviewed.duplicate_source_identities)
        | duplicate_members
    )
    if any(
        by_identity[value].source_identity_sha256 in blocked for value in anchor_ids
    ):
        raise ValueError("mandatory source ID is not eligible for acceptance")
    eligible_count = sum(
        item.source_identity_sha256 not in blocked for item in reviewed.aggregates
    )
    eligibility_manifest = selection.select(
        reviewed,
        migration_version=migration_release_sha,
        limit=eligible_count,
        generated_at=_DETERMINISTIC_SELECTION_TIME,
    )
    selected_ids = tuple(
        value
        for value in eligibility_manifest.ordered_source_identities
        if value not in set(anchor_ids)
    )[:limit]
    if len(selected_ids) != limit:
        raise ValueError("insufficient eligible non-anchor Customer aggregates")

    selected = tuple(_identity(by_identity[value]) for value in selected_ids)
    anchors = tuple(
        sorted(
            (_identity(by_identity[value]) for value in anchor_ids),
            key=lambda item: item.source_identity_sha256,
        )
    )
    values: dict[str, object] = {
        "contract": ACCEPTANCE_COHORT_CONTRACT,
        "adapter": ADAPTER_NAME,
        "source_system": reviewed.source_system,
        "source_sha256": reviewed.source_sha256,
        "schema_version": reviewed.schema_version,
        "transformation_sha256": reviewed.transformation_sha256,
        "review_version": reviewed.review_version,
        "reviewed_output_sha256": reviewed.review_sha256,
        "selection_version": eligibility_manifest.selection_version,
        "eligibility_manifest_sha256": eligibility_manifest.manifest_sha256,
        "migration_release_sha": migration_release_sha,
        "limit": limit,
        "eligible_count": eligible_count,
        "selected": selected,
        "mandatory_anchors": anchors,
    }
    provisional = CustomerAcceptanceCohort.model_construct(
        **values,  # type: ignore[arg-type]
        artifact_sha256="",
    )
    digest = hashlib.sha256(
        _canonical_json(provisional.integrity_payload()).encode()
    ).hexdigest()
    return CustomerAcceptanceCohort.model_validate(
        {**values, "artifact_sha256": digest}
    )

"""Deterministic contracts for sealed HCP.SOURCE.4 acquisition evidence.

This module evaluates metadata and crosswalk evidence only. It performs no HTTP
requests, does not interpret source business meaning, and cannot import data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.operational_migration.hcp_source_acquisition import sha256

CONTRACT_VERSION = "hcp-authoritative-acquisition/v1"


class EvidenceAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    ABSENT = "ABSENT"
    CONFLICTING = "CONFLICTING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CrosswalkState(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    CONTROL_EXPORT_MISSING = "CONTROL_EXPORT_MISSING"
    SOURCE_API_MISSING = "SOURCE_API_MISSING"
    CONFLICTING = "CONFLICTING"


@dataclass(frozen=True)
class CollectionSeal:
    entity: str
    endpoint: str
    record_count: int
    page_sha256s: tuple[str, ...]
    unique_native_id_count: int
    page_1_replay_stable: bool

    def validate(self) -> str:
        if not self.entity or not self.endpoint.startswith("GET "):
            raise ValueError("a read-only source endpoint is required")
        if (
            self.record_count < 0
            or self.unique_native_id_count != self.record_count
        ):
            raise ValueError("record count and unique native identities must agree")
        if not self.page_sha256s or any(
            len(value) != 64 for value in self.page_sha256s
        ):
            raise ValueError("complete page digests are required")
        if not self.page_1_replay_stable:
            raise ValueError("page-one replay must be stable")
        return sha256(
            {
                "contract": CONTRACT_VERSION,
                "entity": self.entity,
                "endpoint": self.endpoint,
                "record_count": self.record_count,
                "page_sha256s": self.page_sha256s,
                "unique_native_id_count": self.unique_native_id_count,
                "page_1_replay_stable": self.page_1_replay_stable,
            }
        )


@dataclass(frozen=True)
class NativeControlEvidence:
    api_native_id: str
    control_reference: str | None
    non_number_corroborators: tuple[str, ...]
    conflicts: tuple[str, ...] = ()

    @property
    def state(self) -> CrosswalkState:
        if self.control_reference is None:
            return CrosswalkState.CONTROL_EXPORT_MISSING
        if self.conflicts:
            return CrosswalkState.CONFLICTING
        if self.non_number_corroborators:
            return CrosswalkState.AVAILABLE
        return CrosswalkState.PARTIAL


def classify_relationship(
    *, parent_present: bool, child_present: bool, values_conflict: bool = False
) -> EvidenceAvailability:
    """Classify observed evidence without inventing a missing relationship."""
    if values_conflict:
        return EvidenceAvailability.CONFLICTING
    if parent_present and child_present:
        return EvidenceAvailability.AVAILABLE
    if parent_present or child_present:
        return EvidenceAvailability.PARTIAL
    return EvidenceAvailability.ABSENT


def seal_reconciliation_summary(summary: dict[str, Any]) -> str:
    """Digest safe aggregate evidence; reject records or source identifiers."""
    forbidden = {"raw_payload", "customer_name", "address", "email", "phone"}
    if forbidden.intersection(summary):
        raise ValueError("raw or identifying source data cannot enter the safe summary")
    return sha256({"contract": CONTRACT_VERSION, "summary": summary})

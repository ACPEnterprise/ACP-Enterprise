"""Machine-bindable HCP.MIGRATION.1A owner and target-readiness contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

CONTRACT_VERSION = "hcp-owner-disposition/v1"


class BlockerClass(StrEnum):
    OWNER_DECISION = "owner_decision"
    EXTERNAL_EVIDENCE = "external_evidence"
    EXPLICIT_EXCEPTION = "explicit_exception"


@dataclass(frozen=True)
class DispositionAlternative:
    identifier: str
    migration_effect: str
    consequence: str
    reversible_before_cutover: bool

    def __post_init__(self) -> None:
        if not self.identifier or not self.migration_effect or not self.consequence:
            raise ValueError("complete disposition alternative evidence is required")


@dataclass(frozen=True)
class OwnerDecisionGroup:
    identifier: str
    affected_count: int
    reason: str
    evidence_sha256: str
    recommended_default: str | None
    alternatives: tuple[DispositionAlternative, ...]
    representative_native_id_sha256s: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.identifier.startswith("HCP1A.") or self.affected_count < 1:
            raise ValueError("stable HCP1A decision identity and count are required")
        if len(self.evidence_sha256) != 64 or not self.alternatives:
            raise ValueError("decision group evidence is incomplete")
        ids = {item.identifier for item in self.alternatives}
        if len(ids) != len(self.alternatives):
            raise ValueError("alternative identifiers must be unique")
        if self.recommended_default is not None and self.recommended_default not in ids:
            raise ValueError("recommended default must identify an alternative")

    @property
    def binding_digest(self) -> str:
        return canonical_sha256(
            {"contract": CONTRACT_VERSION, "decision": asdict(self)}
        )


@dataclass(frozen=True)
class NonProductionTarget:
    environment: str
    database_url: str
    expected_database: str
    production_access_enabled: bool
    preview_access_enabled: bool
    initially_empty_required: bool

    def validate(self) -> str:
        parsed = urlparse(self.database_url)
        database = parsed.path.removeprefix("/")
        if self.environment != "migration_rehearsal":
            raise ValueError("target must be explicitly migration_rehearsal")
        if parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("target host is not isolated")
        if (
            database != self.expected_database
            or database != "acp_hcp_rehearsal_import"
        ):
            raise ValueError("target database identity is not approved")
        if self.production_access_enabled or self.preview_access_enabled:
            raise ValueError("Preview and Production access must be disabled")
        if not self.initially_empty_required:
            raise ValueError("an initially empty target is required")
        return canonical_sha256(
            {
                "environment": self.environment,
                "scheme": parsed.scheme,
                "hostname": parsed.hostname,
                "port": parsed.port,
                "database": database,
                "production_access_enabled": self.production_access_enabled,
                "preview_access_enabled": self.preview_access_enabled,
                "initially_empty_required": self.initially_empty_required,
            }
        )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode()
    ).hexdigest()


def seal_owner_packet(groups: tuple[OwnerDecisionGroup, ...]) -> str:
    identifiers = [group.identifier for group in groups]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("duplicate owner decision identifier")
    return canonical_sha256(
        {
            "contract": CONTRACT_VERSION,
            "groups": [
                {**asdict(group), "binding_digest": group.binding_digest}
                for group in sorted(groups, key=lambda item: item.identifier)
            ],
        }
    )

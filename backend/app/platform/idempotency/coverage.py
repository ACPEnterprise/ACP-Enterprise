"""Deterministic coverage registry for mutating HTTP operations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files

COVERAGE_VERSION = "1"


class MutationClassification(StrEnum):
    REQUIRED = "IDEMPOTENCY_REQUIRED"
    NATURAL = "NATURALLY_IDEMPOTENT"
    APPEND_ONLY = "IMMUTABLE_APPEND_ONLY"
    READ_ONLY = "NON_MUTATING_READ_ONLY"
    EXEMPT = "EXPLICIT_EXEMPTION"


@dataclass(frozen=True, slots=True)
class MutationCoverage:
    method: str
    path: str
    operation_id: str
    domain: str
    classification: MutationClassification
    mechanism: str
    tenant_scope: str
    reason: str

    @property
    def identity(self) -> tuple[str, str]:
        return (self.method, self.path)


@dataclass(frozen=True, slots=True)
class MutationCoverageRegistry:
    entries: tuple[MutationCoverage, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        identities = [entry.identity for entry in self.entries]
        operations = [entry.operation_id for entry in self.entries]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate method/path in idempotency coverage")
        if len(operations) != len(set(operations)):
            raise ValueError("duplicate operation ID in idempotency coverage")
        if self.fingerprint != _fingerprint(self.entries):
            raise ValueError("idempotency coverage fingerprint does not match")

    def by_identity(self) -> dict[tuple[str, str], MutationCoverage]:
        return {entry.identity: entry for entry in self.entries}


def _fingerprint(entries: tuple[MutationCoverage, ...]) -> str:
    payload = [
        {
            "classification": entry.classification.value,
            "domain": entry.domain,
            "mechanism": entry.mechanism,
            "method": entry.method,
            "operation_id": entry.operation_id,
            "path": entry.path,
            "reason": entry.reason,
            "tenant_scope": entry.tenant_scope,
        }
        for entry in sorted(entries, key=lambda item: item.identity)
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_mutation_coverage() -> MutationCoverageRegistry:
    resource = files(__package__).joinpath("mutation-coverage.v1.json")
    raw = json.loads(resource.read_text(encoding="utf-8"))
    if raw.get("schema_version") != COVERAGE_VERSION:
        raise ValueError("unsupported idempotency coverage version")
    entries = tuple(
        MutationCoverage(
            method=item["method"],
            path=item["path"],
            operation_id=item["operation_id"],
            domain=item["domain"],
            classification=MutationClassification(item["classification"]),
            mechanism=item["mechanism"],
            tenant_scope=item["tenant_scope"],
            reason=item["reason"],
        )
        for item in raw["entries"]
    )
    return MutationCoverageRegistry(entries=entries, fingerprint=raw["fingerprint"])


mutation_coverage_registry = load_mutation_coverage()

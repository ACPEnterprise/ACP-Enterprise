from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HandoffStage(str, Enum):
    SEALED_SOURCE = "sealed_source"
    TRANSFORMATION_PLAN = "transformation_plan"
    SOURCE_REPORTED_ENTERPRISE = "source_reported_enterprise"
    RECONCILIATION_REVIEW = "reconciliation_review"
    FINANCE_DISPOSITION = "finance_disposition"
    ACCOUNTING_CORRECTION = "accounting_correction"


@dataclass(frozen=True)
class MigrationHandoff:
    source_manifest_sha256: str
    source_envelope_sha256: str
    transformation_version: str
    source_reported_record_id: str
    reconciliation_finding_ids: tuple[str, ...]
    finance_disposition_id: str | None
    accounting_correction_id: str | None

    def __post_init__(self) -> None:
        if not all(
            (
                self.source_manifest_sha256,
                self.source_envelope_sha256,
                self.transformation_version,
                self.source_reported_record_id,
            )
        ):
            raise ValueError("immutable migration lineage is required")
        if self.accounting_correction_id and not self.finance_disposition_id:
            raise ValueError("Accounting correction requires Finance disposition")


class IntelligenceActor(str, Enum):
    BUSINESS_ECONOMICS = "business_economics"
    BEACON = "beacon"
    LUMINARY = "luminary"
    LIA = "lia"
    ACCOUNTING = "accounting"


@dataclass(frozen=True)
class IntelligenceEvidenceStep:
    actor: IntelligenceActor
    artifact_id: str
    evidence_ids: tuple[str, ...]
    action: str
    posts_accounting_correction: bool = False

    def __post_init__(self) -> None:
        if not self.artifact_id or not self.evidence_ids or not self.action:
            raise ValueError("evidence-bound intelligence step is required")
        if (
            self.posts_accounting_correction
            and self.actor != IntelligenceActor.ACCOUNTING
        ):
            raise ValueError("only Accounting may record a correction")


@dataclass(frozen=True)
class IntelligenceProvingChain:
    steps: tuple[IntelligenceEvidenceStep, ...]

    def __post_init__(self) -> None:
        expected = tuple(IntelligenceActor)
        if tuple(step.actor for step in self.steps) != expected:
            raise ValueError("intelligence proving chain order is invalid")
        source_ids = set(self.steps[0].evidence_ids)
        if any(
            not source_ids.intersection(step.evidence_ids) for step in self.steps[1:]
        ):
            raise ValueError("every step must retain source/conflict lineage")
        if any(step.posts_accounting_correction for step in self.steps[:-1]):
            raise ValueError("non-Accounting step cannot post a correction")

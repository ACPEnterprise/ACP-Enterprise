from __future__ import annotations

import re
from dataclasses import dataclass

from app.qbo_source.economics_evidence import (
    EconomicsEvidenceCategory,
    EconomicsEvidenceState,
    QboEconomicsEvidenceAssessment,
)

from .source_conformance import (
    EconomicComponent,
    EvidenceAssertion,
    EvidenceConfidence,
)

_SHA256 = re.compile(r"^[a-f0-9]{64}$")

_QBO_COMPONENTS = {
    EconomicsEvidenceCategory.REVENUE_ASSERTION: EconomicComponent.REVENUE,
    EconomicsEvidenceCategory.SETTLEMENT_ASSERTION: EconomicComponent.SETTLEMENT,
    EconomicsEvidenceCategory.PROCUREMENT_ASSERTION: EconomicComponent.DIRECT_MATERIAL,
}


@dataclass(frozen=True, slots=True)
class PublicOperationalEvidence:
    """Safe handoff contract; contains no raw Migration payload or economic amount."""

    assertion_id: str
    source_system: str
    source_authority: str
    component: EconomicComponent
    semantic_key: str
    value_digest: str
    evidence_digest: str
    package_digest: str
    confidence: EvidenceConfidence
    satisfied_requirements: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.assertion_id or not self.semantic_key:
            raise ValueError("public evidence identity is required")
        if not self.source_system or not self.source_authority:
            raise ValueError("public source authority is required")
        for digest in (self.value_digest, self.evidence_digest, self.package_digest):
            if not _SHA256.fullmatch(digest):
                raise ValueError("public evidence requires immutable SHA-256 digests")
        if self.confidence is EvidenceConfidence.CONFLICTING:
            raise ValueError("adapters cannot preselect a source conflict")
        if any(
            not item or item.startswith("satisfies:")
            for item in self.satisfied_requirements
        ):
            raise ValueError("satisfied requirement names must be canonical")


def adapt_qbo_economics_evidence(
    assessment: QboEconomicsEvidenceAssessment,
    *,
    semantic_keys: dict[str, str] | None = None,
) -> tuple[EvidenceAssertion, ...]:
    """Adapt source-reported QBO evidence without accepting or reclassifying it."""

    semantic_keys = semantic_keys or {}
    result: list[EvidenceAssertion] = []
    for item in assessment.assertions:
        component = _QBO_COMPONENTS.get(item.category)
        if component is None:
            continue
        semantic_key = semantic_keys.get(
            item.assertion_id, f"qbo:{item.native_entity_type}:{item.native_id}"
        )
        if not semantic_key:
            raise ValueError("semantic reconciliation key cannot be empty")
        result.append(
            EvidenceAssertion(
                assertion_id=item.assertion_id,
                source_system="quickbooks_online",
                source_authority=item.source_authority,
                component=component,
                semantic_key=semantic_key,
                value_digest=item.source_envelope_sha256,
                evidence_digest=item.raw_sha256,
                package_digest=item.source_manifest_sha256,
                confidence=(
                    EvidenceConfidence.PARTIAL
                    if item.state is EconomicsEvidenceState.PARTIAL
                    and assessment.source_manifest_state == "complete"
                    else EvidenceConfidence.UNKNOWN
                ),
                limitations=tuple(sorted(item.limitations)),
            )
        )
    return tuple(sorted(result, key=lambda item: item.assertion_id))


def adapt_public_operational_evidence(
    evidence: tuple[PublicOperationalEvidence, ...],
) -> tuple[EvidenceAssertion, ...]:
    """Consume an owning domain's public evidence contract, never its raw package."""

    return tuple(
        sorted(
            (
                EvidenceAssertion(
                    assertion_id=item.assertion_id,
                    source_system=item.source_system,
                    source_authority=item.source_authority,
                    component=item.component,
                    semantic_key=item.semantic_key,
                    value_digest=item.value_digest,
                    evidence_digest=item.evidence_digest,
                    package_digest=item.package_digest,
                    confidence=item.confidence,
                    limitations=tuple(
                        sorted(
                            (*item.limitations,)
                            + tuple(
                                f"satisfies:{requirement}"
                                for requirement in item.satisfied_requirements
                            )
                        )
                    ),
                )
                for item in evidence
            ),
            key=lambda item: item.assertion_id,
        )
    )

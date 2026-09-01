from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any
from uuid import UUID, uuid5

from app.business_economics.source_completeness import source_completeness_matrix

from .contracts import (
    LUMINARY_BRIEFING_VERSION,
    LUMINARY_FINDING_VERSION,
    EvidenceQuality,
    EvidenceReference,
    FindingClass,
    FindingType,
    LuminaryEvidencePackage,
    LuminaryFinding,
    MeasuredObservation,
    OwnerBriefing,
)

LUMINARY_ENGINE_VERSION = "luminary.deterministic-engine.v1"
LUMINARY_NAMESPACE = UUID("acb71ed5-64a4-5ef2-a899-10280405e56f")


class LuminaryIntegrityError(ValueError):
    """Raised when admitted source evidence cannot support interpretation."""


def canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class LuminaryEngine:
    def analyze(self, package: LuminaryEvidencePackage) -> tuple[LuminaryFinding, ...]:
        self._verify_package(package)
        economics = package.economics
        quality = EvidenceQuality(str(economics.get("quality_state", "unavailable")))
        findings: list[LuminaryFinding] = []
        if quality is EvidenceQuality.CONFLICTING:
            findings.append(
                self._finding(
                    package,
                    FindingClass.CONFLICTING_EVIDENCE,
                    FindingType.MISSING_EVIDENCE,
                    "Conflicting profitability evidence",
                    "Owner profitability interpretation is withheld because admitted evidence conflicts.",
                    (),
                    0,
                    quality,
                    "Conflicting source evidence prevents a reliable business interpretation.",
                    (
                        "No profitability direction is inferred while evidence conflicts.",
                    ),
                    ("Resolve the conflicting admitted Economics evidence.",),
                )
            )
            return tuple(findings)
        if quality is EvidenceQuality.UNAVAILABLE:
            findings.append(
                self._finding(
                    package,
                    FindingClass.INSUFFICIENT_EVIDENCE,
                    FindingType.MISSING_EVIDENCE,
                    "Profitability evidence is unavailable",
                    "No complete admitted Job profitability exists for this period.",
                    (),
                    0,
                    quality,
                    str(
                        economics.get(
                            "explanation", "Required evidence is unavailable."
                        )
                    ),
                    ("No revenue, cost, margin, or causal conclusion was generated.",),
                    ("Inspect Economics evidence and attribution readiness.",),
                )
            )
        else:
            findings.extend(self._performance_findings(package, quality))
            findings.extend(self._comparison_findings(package, quality))
            findings.extend(self._branch_findings(package, quality))
        readiness = self._mapping(economics.get("readiness"))
        if readiness.get("allocation_policy") != "ready":
            findings.append(
                self._finding(
                    package,
                    FindingClass.POLICY_REQUIRED,
                    FindingType.ALLOCATION_POLICY,
                    "Fully allocated profitability requires policy",
                    "Direct contribution may be available, but fully allocated profitability is not authoritative.",
                    (),
                    self._confidence(economics),
                    quality,
                    "No approved indirect-cost allocation policy was applied.",
                    (
                        "Luminary does not choose overhead, fleet, facility, or administrative allocation policy.",
                    ),
                    ("Review the Economics allocation-policy readiness decision.",),
                )
            )
        completeness = source_completeness_matrix(economics)
        exceptions = self._sequence(completeness.get("exceptions"))
        if exceptions:
            named = tuple(
                str(item.get("source"))
                for item in exceptions[:10]
                if isinstance(item, dict)
            )
            findings.append(
                self._finding(
                    package,
                    FindingClass.INSUFFICIENT_EVIDENCE,
                    FindingType.SOURCE_READINESS,
                    "Economic evidence limits the owner conclusion",
                    f"{len(exceptions)} admitted source-readiness exception(s) remain for this period.",
                    (),
                    self._confidence(economics),
                    quality,
                    "Luminary reports the Economics readiness result without substituting missing values.",
                    tuple(f"{name} is not AVAILABLE." for name in named),
                    tuple(
                        f"Inspect {name.replace('_', ' ')} authority."
                        for name in named[:3]
                    ),
                )
            )
        for signal in package.beacon_conditions:
            evidence = EvidenceReference(
                "beacon", "signal", signal.signal_id, signal.evidence_digest
            )
            findings.append(
                self._finding(
                    package,
                    FindingClass.OBSERVED_FACT,
                    FindingType.BEACON_ATTENTION,
                    signal.title,
                    f"Beacon has an active {signal.severity} condition related to this owner briefing.",
                    (),
                    100,
                    quality,
                    "Luminary references the existing Beacon condition; Beacon retains lifecycle authority.",
                    ("No operational cause or remediation was inferred.",),
                    (
                        "Open the related Beacon signal for ownership and workflow state.",
                    ),
                    extra_evidence=(evidence,),
                )
            )
        return tuple(
            sorted(
                findings,
                key=lambda item: (item.finding_type.value, item.finding_digest),
            )
        )

    def briefing(
        self, package: LuminaryEvidencePackage, findings: tuple[LuminaryFinding, ...]
    ) -> OwnerBriefing:
        sections = []
        for name, types in (
            (
                "business_performance",
                {FindingType.BUSINESS_PERFORMANCE, FindingType.PERIOD_CHANGE},
            ),
            (
                "profitability",
                {
                    FindingType.PROFITABLE_JOB,
                    FindingType.UNPROFITABLE_JOB,
                    FindingType.BRANCH_COMPARISON,
                },
            ),
            (
                "cost_drivers",
                {FindingType.LABOR_COST_CHANGE, FindingType.MATERIAL_COST_CHANGE},
            ),
            ("attention", {FindingType.BEACON_ATTENTION}),
            (
                "readiness",
                {
                    FindingType.MISSING_EVIDENCE,
                    FindingType.ALLOCATION_POLICY,
                    FindingType.SOURCE_READINESS,
                },
            ),
        ):
            ids = tuple(
                item.finding_id for item in findings if item.finding_type in types
            )
            if ids:
                sections.append((name, ids))
        quality = self._briefing_quality(findings)
        payload = {
            "version": LUMINARY_BRIEFING_VERSION,
            "company_id": str(package.company_id),
            "branch_id": str(package.branch_id) if package.branch_id else None,
            "period": [
                package.period_start.isoformat(),
                package.period_end.isoformat(),
            ],
            "package_digest": package.package_digest,
            "findings": [item.finding_digest for item in findings],
            "sections": [
                (name, [str(value) for value in ids]) for name, ids in sections
            ],
            "completeness": quality.value,
        }
        digest = canonical_digest(payload)
        return OwnerBriefing(
            briefing_id=uuid5(LUMINARY_NAMESPACE, f"briefing:{digest}"),
            company_id=package.company_id,
            branch_id=package.branch_id,
            period_start=package.period_start,
            period_end=package.period_end,
            evidence_package_digest=package.package_digest,
            finding_ids=tuple(item.finding_id for item in findings),
            finding_digests=tuple(item.finding_digest for item in findings),
            sections=tuple(sections),
            completeness=quality,
            summary=self._briefing_summary(findings, quality),
            briefing_digest=digest,
            generated_at=package.generated_at,
        )

    def _performance_findings(
        self, package: LuminaryEvidencePackage, quality: EvidenceQuality
    ) -> list[LuminaryFinding]:
        economics = package.economics
        totals = self._mapping(economics.get("totals"))
        currency = str(economics.get("currency") or "USD")
        observations = tuple(
            MeasuredObservation(
                key, self._integer(totals.get(key)), currency, "minor_currency"
            )
            for key in ("revenue", "labor", "materials", "gross_profit", "net_profit")
        )
        values = [value.value_minor for value in observations]
        results = [
            self._finding(
                package,
                FindingClass.OBSERVED_FACT,
                FindingType.BUSINESS_PERFORMANCE,
                "Business performance from admitted Economics evidence",
                "Revenue, direct costs, and contribution are presented from accepted Economics results.",
                observations,
                self._confidence(economics),
                quality,
                "Luminary preserved the authoritative Economics totals without recalculation.",
                tuple(
                    ["One or more components remain unavailable."]
                    if any(value is None for value in values)
                    else ()
                ),
                ("Inspect Job and component lineage for the material values.",),
            )
        ]
        jobs = [
            item
            for item in self._sequence(economics.get("jobs"))
            if isinstance(item, dict)
        ]
        comparable = [
            item for item in jobs if isinstance(item.get("contribution_minor"), int)
        ]
        if comparable:
            strongest = max(
                comparable, key=lambda item: int(item["contribution_minor"])
            )
            weakest = min(comparable, key=lambda item: int(item["contribution_minor"]))
            results.append(self._job_finding(package, strongest, True, quality))
            if weakest is not strongest or int(weakest["contribution_minor"]) < 0:
                results.append(self._job_finding(package, weakest, False, quality))
        return results

    def _job_finding(
        self,
        package: LuminaryEvidencePackage,
        job: dict[str, Any],
        strongest: bool,
        quality: EvidenceQuality,
    ) -> LuminaryFinding:
        contribution = int(job["contribution_minor"])
        negative = contribution < 0
        classification = (
            FindingType.UNPROFITABLE_JOB if negative else FindingType.PROFITABLE_JOB
        )
        label = str(job.get("job_number") or "Admitted Job")
        position = "strongest" if strongest else "weakest"
        return self._finding(
            package,
            FindingClass.OBSERVED_FACT,
            classification,
            f"{label} is the {position} measured Job in this scope",
            f"The Job has measured contribution of {contribution} minor currency units.",
            (
                MeasuredObservation(
                    "job_contribution",
                    contribution,
                    str(job.get("currency") or "USD"),
                    "minor_currency",
                ),
            ),
            int(job.get("confidence_percent") or 0),
            EvidenceQuality(str(job.get("quality_state") or quality.value)),
            "The ranking compares only admitted Jobs with measured contribution in this period.",
            ("The finding does not claim why the Job performed this way.",),
            ("Inspect the Job's revenue, labor, material, and allocation lineage.",),
        )

    def _comparison_findings(
        self, package: LuminaryEvidencePackage, quality: EvidenceQuality
    ) -> list[LuminaryFinding]:
        comparison = self._mapping(package.economics.get("comparison"))
        if comparison.get("state") != "available":
            return []
        currency = str(package.economics.get("currency") or "USD")
        changes = {
            "revenue": self._integer(comparison.get("revenue_change_minor")),
            "contribution": self._integer(comparison.get("contribution_change_minor")),
            "labor": self._integer(comparison.get("labor_change_minor")),
            "materials": self._integer(comparison.get("materials_change_minor")),
        }
        result = [
            self._finding(
                package,
                FindingClass.MEASURED_COMPARISON,
                FindingType.PERIOD_CHANGE,
                "Business performance changed from the comparable period",
                "The comparison uses complete admitted populations for equal-length periods.",
                tuple(
                    MeasuredObservation(
                        key, value, currency, "minor_currency", change_minor=value
                    )
                    for key, value in changes.items()
                ),
                self._confidence(package.economics),
                quality,
                str(comparison.get("explanation") or "Measured period movement."),
                ("Period movement does not prove causality.",),
                (
                    "Inspect component and Job movements contributing to the comparison.",
                ),
            )
        ]
        for metric, finding_type in (
            ("labor", FindingType.LABOR_COST_CHANGE),
            ("materials", FindingType.MATERIAL_COST_CHANGE),
        ):
            value = changes[metric]
            if value:
                result.append(
                    self._finding(
                        package,
                        FindingClass.SUPPORTED_ASSOCIATION,
                        finding_type,
                        f"{metric.title()} cost moved alongside contribution",
                        f"Measured {metric} cost changed by {value} minor currency units in the same comparison.",
                        (
                            MeasuredObservation(
                                f"{metric}_change",
                                value,
                                currency,
                                "minor_currency",
                                change_minor=value,
                            ),
                        ),
                        self._confidence(package.economics),
                        quality,
                        "This is a measured co-movement, not a claim that the cost change caused margin movement.",
                        (
                            "Other admitted components may also contribute to the period change.",
                        ),
                        (
                            f"Inspect {metric} evidence and attribution before drawing a causal conclusion.",
                        ),
                    )
                )
        return result

    def _branch_findings(
        self, package: LuminaryEvidencePackage, quality: EvidenceQuality
    ) -> list[LuminaryFinding]:
        branches = [
            item
            for item in self._sequence(package.economics.get("branches"))
            if isinstance(item, dict)
        ]
        complete = [
            item for item in branches if item.get("quality_state") == "complete"
        ]
        if len(complete) < 2:
            return []
        strongest = max(
            complete, key=lambda item: int(item.get("contribution_minor") or 0)
        )
        weakest = min(
            complete, key=lambda item: int(item.get("contribution_minor") or 0)
        )
        return [
            self._finding(
                package,
                FindingClass.MEASURED_COMPARISON,
                FindingType.BRANCH_COMPARISON,
                "Branch contribution differs across admitted populations",
                f"{strongest['label']} has the strongest and {weakest['label']} the weakest measured contribution in this scope.",
                (
                    MeasuredObservation(
                        "strongest_branch_contribution",
                        int(strongest["contribution_minor"]),
                        str(package.economics.get("currency") or "USD"),
                        "minor_currency",
                    ),
                    MeasuredObservation(
                        "weakest_branch_contribution",
                        int(weakest["contribution_minor"]),
                        str(package.economics.get("currency") or "USD"),
                        "minor_currency",
                    ),
                ),
                self._confidence(package.economics),
                quality,
                "The comparison uses reconciled admitted Job populations by authoritative Branch.",
                (
                    "Different service mix or evidence coverage may affect interpretation; no cause is asserted.",
                ),
                ("Compare Job mix and component evidence within each Branch.",),
            )
        ]

    def _finding(
        self,
        package: LuminaryEvidencePackage,
        finding_class: FindingClass,
        finding_type: FindingType,
        title: str,
        summary: str,
        observations: tuple[MeasuredObservation, ...],
        confidence: int,
        completeness: EvidenceQuality,
        explanation: str,
        limitations: tuple[str, ...],
        investigate_next: tuple[str, ...],
        *,
        extra_evidence: tuple[EvidenceReference, ...] = (),
    ) -> LuminaryFinding:
        evidence = tuple(
            sorted(
                (*package.economics_results, *extra_evidence),
                key=lambda item: (item.source_domain, item.record_id, item.digest),
            )
        )
        payload = {
            "definition_version": LUMINARY_FINDING_VERSION,
            "engine_version": LUMINARY_ENGINE_VERSION,
            "company_id": str(package.company_id),
            "branch_id": str(package.branch_id) if package.branch_id else None,
            "period": [
                package.period_start.isoformat(),
                package.period_end.isoformat(),
            ],
            "package_digest": package.package_digest,
            "class": finding_class.value,
            "type": finding_type.value,
            "title": title,
            "summary": summary,
            "observations": [asdict(item) for item in observations],
            "evidence": [asdict(item) for item in evidence],
            "confidence": confidence,
            "completeness": completeness.value,
            "explanation": explanation,
            "limitations": limitations,
            "investigate_next": investigate_next,
        }
        digest = canonical_digest(payload)
        return LuminaryFinding(
            finding_id=uuid5(LUMINARY_NAMESPACE, f"finding:{digest}"),
            company_id=package.company_id,
            branch_id=package.branch_id,
            period_start=package.period_start,
            period_end=package.period_end,
            finding_class=finding_class,
            finding_type=finding_type,
            title=title,
            summary=summary,
            observations=observations,
            evidence=evidence,
            evidence_package_digest=package.package_digest,
            confidence_percent=max(0, min(confidence, 100)),
            completeness=completeness,
            freshness=str(package.economics.get("quality_state", "unavailable")),
            explanation=explanation,
            limitations=limitations,
            investigate_next=investigate_next,
            engine_version=LUMINARY_ENGINE_VERSION,
            definition_version=LUMINARY_FINDING_VERSION,
            finding_digest=digest,
            generated_at=package.generated_at,
        )

    @staticmethod
    def _verify_package(package: LuminaryEvidencePackage) -> None:
        if len(package.package_digest) != 64:
            raise LuminaryIntegrityError("evidence package digest is invalid")
        expected = canonical_digest(
            {
                "company_id": str(package.company_id),
                "branch_id": str(package.branch_id) if package.branch_id else None,
                "period": [
                    package.period_start.isoformat(),
                    package.period_end.isoformat(),
                ],
                "economics": package.economics,
                "economics_results": [
                    asdict(item) for item in package.economics_results
                ],
                "beacon_conditions": [
                    asdict(item) for item in package.beacon_conditions
                ],
            }
        )
        if expected != package.package_digest:
            raise LuminaryIntegrityError("evidence package integrity check failed")

    @staticmethod
    def _mapping(value: object) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _integer(value: object) -> int | None:
        return value if isinstance(value, int) else None

    @staticmethod
    def _sequence(value: object) -> list[object]:
        return value if isinstance(value, list) else []

    @staticmethod
    def _confidence(economics: dict[str, object]) -> int:
        jobs = [
            item
            for item in LuminaryEngine._sequence(economics.get("jobs"))
            if isinstance(item, dict)
        ]
        values = [int(item.get("confidence_percent") or 0) for item in jobs]
        return min(values) if values else 0

    @staticmethod
    def _briefing_quality(findings: tuple[LuminaryFinding, ...]) -> EvidenceQuality:
        values = {item.completeness for item in findings}
        for quality in (
            EvidenceQuality.CONFLICTING,
            EvidenceQuality.UNAVAILABLE,
            EvidenceQuality.STALE,
            EvidenceQuality.PARTIAL,
        ):
            if quality in values:
                return quality
        return EvidenceQuality.COMPLETE if findings else EvidenceQuality.UNAVAILABLE

    @staticmethod
    def _briefing_summary(
        findings: tuple[LuminaryFinding, ...], quality: EvidenceQuality
    ) -> str:
        if quality is EvidenceQuality.CONFLICTING:
            return "Evidence conflicts; Luminary withheld business conclusions."
        if quality is EvidenceQuality.UNAVAILABLE:
            return "Evidence is unavailable; Luminary identified what must be resolved before interpretation."
        return f"Luminary identified {len(findings)} evidence-bound owner finding(s); limitations remain explicit."

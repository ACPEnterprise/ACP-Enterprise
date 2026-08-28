from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import NoReturn
from uuid import UUID

from .findings import EconomicInconsistencyFinding, SubjectKind
from .measurement_contract import (
    ContributionMeasurementGate,
    MeasurementEvidenceInput,
    PolicyPrerequisite,
    evaluate_contribution_measurement_gate,
)

MEASUREMENT_PACKAGE_VERSION = "eco.measurement.package.v1"


class MeasurementPackageIntegrityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MeasurementReadinessPackage:
    package_id: str
    package_digest: str
    package_version: str
    company_id: UUID
    branch_id: UUID | None
    subject_id: str
    subject_kind: SubjectKind
    reconciliation_key: str
    measurement_definition_version: str
    evidence: tuple[MeasurementEvidenceInput, ...]
    findings: tuple[EconomicInconsistencyFinding, ...]
    policy_dependencies: tuple[PolicyPrerequisite, ...]
    gate: ContributionMeasurementGate


def seal_measurement_readiness_package(
    *,
    company_id: UUID,
    branch_id: UUID | None,
    gate: ContributionMeasurementGate,
    findings: tuple[EconomicInconsistencyFinding, ...],
) -> MeasurementReadinessPackage:
    evidence = tuple(sorted(gate.evidence, key=lambda item: item.input_id))
    relevant_findings = tuple(
        sorted(
            (
                item
                for item in findings
                if item.subject_id == gate.subject_id
                and item.reconciliation_key == gate.reconciliation_key
            ),
            key=lambda item: item.finding_id,
        )
    )
    policies = tuple(
        sorted(gate.policy_dependencies, key=lambda item: item.dependency_id)
    )
    _verify_boundaries(
        company_id=company_id,
        branch_id=branch_id,
        gate=gate,
        evidence=evidence,
        findings=relevant_findings,
    )
    replayed = _replay_gate(gate, evidence, relevant_findings, policies)
    if replayed != gate:
        raise MeasurementPackageIntegrityError(
            "measurement gate is inconsistent with packaged evidence"
        )
    canonical = _canonical(
        company_id=company_id,
        branch_id=branch_id,
        gate=gate,
        evidence=evidence,
        findings=relevant_findings,
        policies=policies,
    )
    digest = _digest(canonical)
    package = MeasurementReadinessPackage(
        package_id=f"eco-measurement-package:{digest}",
        package_digest=digest,
        package_version=MEASUREMENT_PACKAGE_VERSION,
        company_id=company_id,
        branch_id=branch_id,
        subject_id=gate.subject_id,
        subject_kind=gate.subject_kind,
        reconciliation_key=gate.reconciliation_key,
        measurement_definition_version=gate.definition_version,
        evidence=evidence,
        findings=relevant_findings,
        policy_dependencies=policies,
        gate=gate,
    )
    verify_measurement_readiness_package(package)
    return package


def verify_measurement_readiness_package(
    package: MeasurementReadinessPackage,
) -> None:
    if package.package_version != MEASUREMENT_PACKAGE_VERSION:
        _invalid("unsupported package version")
    if package.package_id != f"eco-measurement-package:{package.package_digest}":
        _invalid("package identity does not match digest")
    if package.measurement_definition_version != package.gate.definition_version:
        _invalid("measurement definition version changed")
    if (
        package.subject_id != package.gate.subject_id
        or package.subject_kind is not package.gate.subject_kind
        or package.reconciliation_key != package.gate.reconciliation_key
    ):
        _invalid("package subject boundary does not match gate")
    _verify_boundaries(
        company_id=package.company_id,
        branch_id=package.branch_id,
        gate=package.gate,
        evidence=package.evidence,
        findings=package.findings,
    )
    replayed = _replay_gate(
        package.gate,
        package.evidence,
        package.findings,
        package.policy_dependencies,
    )
    if replayed != package.gate:
        _invalid("packaged measurement gate fails deterministic replay")
    expected = _digest(
        _canonical(
            company_id=package.company_id,
            branch_id=package.branch_id,
            gate=package.gate,
            evidence=package.evidence,
            findings=package.findings,
            policies=package.policy_dependencies,
        )
    )
    if expected != package.package_digest:
        _invalid("package contents do not match package digest")


def _verify_boundaries(
    *,
    company_id: UUID,
    branch_id: UUID | None,
    gate: ContributionMeasurementGate,
    evidence: tuple[MeasurementEvidenceInput, ...],
    findings: tuple[EconomicInconsistencyFinding, ...],
) -> None:
    if any(item.company_id != company_id for item in evidence):
        _invalid("measurement evidence Company boundary mismatch")
    if any(item.branch_id != branch_id for item in evidence):
        _invalid("measurement evidence Branch boundary mismatch")
    if any(
        item.subject_id != gate.subject_id
        or item.reconciliation_key != gate.reconciliation_key
        for item in evidence
    ):
        _invalid("measurement evidence subject boundary mismatch")
    if any(
        item.subject_id != gate.subject_id
        or item.reconciliation_key != gate.reconciliation_key
        for item in findings
    ):
        _invalid("finding subject boundary mismatch")


def _replay_gate(
    gate: ContributionMeasurementGate,
    evidence: tuple[MeasurementEvidenceInput, ...],
    findings: tuple[EconomicInconsistencyFinding, ...],
    policies: tuple[PolicyPrerequisite, ...],
) -> ContributionMeasurementGate:
    return evaluate_contribution_measurement_gate(
        subject_id=gate.subject_id,
        subject_kind=gate.subject_kind,
        reconciliation_key=gate.reconciliation_key,
        required_components=tuple(item.component for item in gate.components),
        evidence=evidence,
        findings=findings,
        policy_dependencies=policies,
    )


def _canonical(
    *,
    company_id: UUID,
    branch_id: UUID | None,
    gate: ContributionMeasurementGate,
    evidence: tuple[MeasurementEvidenceInput, ...],
    findings: tuple[EconomicInconsistencyFinding, ...],
    policies: tuple[PolicyPrerequisite, ...],
) -> dict[str, object]:
    return {
        "package_version": MEASUREMENT_PACKAGE_VERSION,
        "company_id": str(company_id),
        "branch_id": str(branch_id) if branch_id else None,
        "subject_id": gate.subject_id,
        "subject_kind": gate.subject_kind.value,
        "reconciliation_key": gate.reconciliation_key,
        "measurement_definition_version": gate.definition_version,
        "evidence": [_evidence_document(item) for item in evidence],
        "findings": [_finding_document(item) for item in findings],
        "policies": [_policy_document(item) for item in policies],
        "gate": {
            "gate_id": gate.gate_id,
            "state": gate.state.value,
            "components": [
                {
                    "component": item.component.value,
                    "state": item.state.value,
                    "evidence_ids": item.evidence_ids,
                    "source_authorities": item.source_authorities,
                    "blocking_reasons": item.blocking_reasons,
                }
                for item in gate.components
            ],
            "blocking_components": tuple(
                item.value for item in gate.blocking_components
            ),
            "explanation_facts": gate.explanation_facts,
        },
    }


def _evidence_document(item: MeasurementEvidenceInput) -> dict[str, object]:
    return {
        "input_id": item.input_id,
        "definition_version": item.definition_version,
        "company_id": str(item.company_id) if item.company_id else None,
        "branch_id": str(item.branch_id) if item.branch_id else None,
        "subject_id": item.subject_id,
        "reconciliation_key": item.reconciliation_key,
        "component": item.component.value,
        "source_authority": item.source_authority,
        "evidence_state": item.evidence_state.value,
        "confidence": item.confidence.value,
        "source_value": str(item.source_value)
        if item.source_value is not None
        else None,
        "currency": item.currency,
        "unit": item.unit,
        "effective_date": item.effective_date.isoformat()
        if item.effective_date
        else None,
        "as_of": item.as_of.isoformat() if item.as_of else None,
        "accepted_for_measurement": item.accepted_for_measurement,
        "limitations": item.limitations,
        "evidence_digest": item.evidence_digest,
        "value_digest": item.value_digest,
        "source_package_digest": item.package_digest,
    }


def _finding_document(item: EconomicInconsistencyFinding) -> dict[str, object]:
    return {
        "finding_id": item.finding_id,
        "definition_version": item.definition_version,
        "finding_type": item.finding_type.value,
        "subject_id": item.subject_id,
        "reconciliation_key": item.reconciliation_key,
        "component": item.component.value,
        "state": item.state.value,
        "confidence": item.confidence.value,
        "measured_condition": item.measured_condition,
        "source_authorities": item.source_authorities,
        "limitations": item.limitations,
        "explanation_facts": item.explanation_facts,
        "evidence": [
            {
                "assertion_id": evidence.assertion_id,
                "source_system": evidence.source_system,
                "source_authority": evidence.source_authority,
                "confidence": evidence.confidence.value,
                "evidence_digest": evidence.evidence_digest,
                "value_digest": evidence.value_digest,
                "package_digest": evidence.package_digest,
                "limitations": evidence.limitations,
            }
            for evidence in item.evidence
        ],
    }


def _policy_document(item: PolicyPrerequisite) -> dict[str, object]:
    return {
        "dependency_id": item.dependency_id,
        "component": item.component.value,
        "state": item.state.value,
        "authority": item.authority,
        "policy_version": item.policy_version,
        "evidence_digest": item.evidence_digest,
    }


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _invalid(message: str) -> NoReturn:
    raise MeasurementPackageIntegrityError(message)

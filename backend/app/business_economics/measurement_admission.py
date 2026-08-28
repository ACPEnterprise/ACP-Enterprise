from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from .findings import FindingState, SubjectKind
from .measurement_contract import (
    MeasurementComponent,
    MeasurementGateState,
    PrerequisiteState,
)
from .measurement_package import (
    MEASUREMENT_PACKAGE_VERSION,
    MeasurementPackageIntegrityError,
    MeasurementReadinessPackage,
    verify_measurement_readiness_package,
)

MEASUREMENT_ADMISSION_VERSION = "eco.measurement.admission.v1"


class AdmissionState(str, Enum):
    ADMITTED = "admitted"
    REJECTED_NOT_MEASURABLE = "rejected_not_measurable"
    REJECTED_PARTIAL = "rejected_partial"
    REJECTED_CONFLICTING = "rejected_conflicting"
    REJECTED_UNRESOLVED_POLICY = "rejected_unresolved_policy"
    REJECTED_INTEGRITY = "rejected_integrity"
    REJECTED_SCOPE = "rejected_scope"
    REJECTED_AUTHORITY = "rejected_authority"


@dataclass(frozen=True, slots=True)
class CalculationAdmissionRequest:
    company_id: UUID
    branch_id: UUID | None
    subject_id: str
    subject_kind: SubjectKind
    reconciliation_key: str
    supported_package_versions: tuple[str, ...]
    supported_measurement_versions: tuple[str, ...]
    permitted_accepted_authorities: tuple[str, ...]
    required_policy_dependency_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.subject_id or not self.reconciliation_key:
            raise ValueError("admission scope identities are required")
        if (
            not self.supported_package_versions
            or not self.supported_measurement_versions
        ):
            raise ValueError("supported definition versions are required")
        if len(set(self.permitted_accepted_authorities)) != len(
            self.permitted_accepted_authorities
        ):
            raise ValueError("permitted authorities must be unique")


@dataclass(frozen=True, slots=True)
class CalculationAdmissionResult:
    admission_id: str
    result_digest: str
    admission_version: str
    package_id: str
    package_digest: str
    state: AdmissionState
    rejection_reasons: tuple[str, ...]
    blocking_components: tuple[MeasurementComponent, ...]
    unresolved_policy_ids: tuple[str, ...]
    authority_limitations: tuple[str, ...]
    explanation_facts: tuple[str, ...]


def evaluate_calculation_admission(
    package: MeasurementReadinessPackage,
    request: CalculationAdmissionRequest,
) -> CalculationAdmissionResult:
    reasons: set[str] = set()
    integrity_valid = True
    try:
        verify_measurement_readiness_package(package)
    except MeasurementPackageIntegrityError:
        integrity_valid = False
        reasons.add("package_integrity_verification_failed")

    scope_valid = _scope_matches(package, request)
    if not scope_valid:
        reasons.add("requested_scope_does_not_match_package")
    versions_valid = (
        package.package_version in request.supported_package_versions
        and package.measurement_definition_version
        in request.supported_measurement_versions
        and package.package_version == MEASUREMENT_PACKAGE_VERSION
    )
    if not versions_valid:
        reasons.add("unsupported_definition_version")

    unaccepted = tuple(
        sorted(
            item.input_id
            for item in package.evidence
            if not item.accepted_for_measurement
        )
    )
    disallowed_authorities = tuple(
        sorted(
            {
                item.source_authority
                for item in package.evidence
                if item.source_authority not in request.permitted_accepted_authorities
            }
        )
    )
    authority_limitations = tuple(
        sorted(
            {
                *(f"unaccepted:{item}" for item in unaccepted),
                *(f"authority_not_permitted:{item}" for item in disallowed_authorities),
            }
        )
    )
    if authority_limitations:
        reasons.add("evidence_authority_or_acceptance_not_admissible")

    policy_by_id = {item.dependency_id: item for item in package.policy_dependencies}
    unresolved_policies = tuple(
        sorted(
            dependency_id
            for dependency_id in request.required_policy_dependency_ids
            if dependency_id not in policy_by_id
            or policy_by_id[dependency_id].state is PrerequisiteState.UNRESOLVED
        )
    )
    unresolved_policies = tuple(
        sorted(
            {
                *unresolved_policies,
                *(
                    item.dependency_id
                    for item in package.policy_dependencies
                    if item.state is PrerequisiteState.UNRESOLVED
                ),
            }
        )
    )
    if unresolved_policies:
        reasons.add("calculation_required_policy_unresolved")

    if (
        any(item.state is FindingState.CONFLICTING for item in package.gate.components)
        or package.gate.state is MeasurementGateState.CONFLICTING
    ):
        reasons.add("measurement_evidence_conflicting")
    if package.gate.state is MeasurementGateState.PARTIALLY_MEASURABLE:
        reasons.add("measurement_gate_partial")
    elif package.gate.state is MeasurementGateState.NOT_MEASURABLE:
        reasons.add("measurement_gate_not_measurable")

    state = _admission_state(
        integrity_valid=integrity_valid and versions_valid,
        scope_valid=scope_valid,
        authority_valid=not authority_limitations,
        unresolved_policies=unresolved_policies,
        gate_state=package.gate.state,
    )
    if state is AdmissionState.ADMITTED and reasons:
        raise AssertionError("admitted package cannot retain rejection reasons")
    canonical = {
        "admission_version": MEASUREMENT_ADMISSION_VERSION,
        "package_id": package.package_id,
        "package_digest": package.package_digest,
        "request": {
            "company_id": str(request.company_id),
            "branch_id": str(request.branch_id) if request.branch_id else None,
            "subject_id": request.subject_id,
            "subject_kind": request.subject_kind.value,
            "reconciliation_key": request.reconciliation_key,
            "supported_package_versions": request.supported_package_versions,
            "supported_measurement_versions": request.supported_measurement_versions,
            "permitted_accepted_authorities": tuple(
                sorted(request.permitted_accepted_authorities)
            ),
            "required_policy_dependency_ids": tuple(
                sorted(request.required_policy_dependency_ids)
            ),
        },
        "state": state.value,
        "rejection_reasons": tuple(sorted(reasons)),
        "blocking_components": tuple(
            item.value for item in package.gate.blocking_components
        ),
        "unresolved_policy_ids": unresolved_policies,
        "authority_limitations": authority_limitations,
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return CalculationAdmissionResult(
        admission_id=f"eco-calculation-admission:{digest}",
        result_digest=digest,
        admission_version=MEASUREMENT_ADMISSION_VERSION,
        package_id=package.package_id,
        package_digest=package.package_digest,
        state=state,
        rejection_reasons=tuple(sorted(reasons)),
        blocking_components=package.gate.blocking_components,
        unresolved_policy_ids=unresolved_policies,
        authority_limitations=authority_limitations,
        explanation_facts=(
            f"package_integrity={'valid' if integrity_valid else 'invalid'}",
            f"scope={'valid' if scope_valid else 'invalid'}",
            f"gate={package.gate.state.value}",
            f"admission={state.value}",
        ),
    )


def _scope_matches(
    package: MeasurementReadinessPackage, request: CalculationAdmissionRequest
) -> bool:
    return (
        package.company_id == request.company_id
        and package.branch_id == request.branch_id
        and package.subject_id == request.subject_id
        and package.subject_kind is request.subject_kind
        and package.reconciliation_key == request.reconciliation_key
    )


def _admission_state(
    *,
    integrity_valid: bool,
    scope_valid: bool,
    authority_valid: bool,
    unresolved_policies: tuple[str, ...],
    gate_state: MeasurementGateState,
) -> AdmissionState:
    if not integrity_valid:
        return AdmissionState.REJECTED_INTEGRITY
    if not scope_valid:
        return AdmissionState.REJECTED_SCOPE
    if not authority_valid:
        return AdmissionState.REJECTED_AUTHORITY
    if unresolved_policies:
        return AdmissionState.REJECTED_UNRESOLVED_POLICY
    if gate_state is MeasurementGateState.CONFLICTING:
        return AdmissionState.REJECTED_CONFLICTING
    if gate_state is MeasurementGateState.PARTIALLY_MEASURABLE:
        return AdmissionState.REJECTED_PARTIAL
    if gate_state is MeasurementGateState.NOT_MEASURABLE:
        return AdmissionState.REJECTED_NOT_MEASURABLE
    return AdmissionState.ADMITTED

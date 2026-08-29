"""Bind deterministic profitability computation to accepted Economics readiness.

The computation engine is deliberately persistence- and source-neutral.  This
bridge is the current-authority boundary: it refuses to calculate unless the
existing measurement package admission has already proved source authority,
scope, completeness, policy, and integrity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .measurement_admission import AdmissionState, CalculationAdmissionResult
from .profitability_computation import ProfitabilityComputationRequest
from .profitability_engine import (
    AcquiredProfitabilityFact,
    AllocatedProfitabilityCost,
    ReconciledProfitabilityEngine,
    ReconciledProfitabilityResult,
)

PROFITABILITY_ADMISSION_BRIDGE_VERSION = "eco.profitability.admission-bridge.v1"


class ProfitabilityAdmissionError(ValueError):
    """Raised when current Economics authority has not admitted calculation."""


@dataclass(frozen=True, slots=True)
class AdmittedProfitabilityResult:
    admission_id: str
    admission_digest: str
    package_id: str
    package_digest: str
    computation: ReconciledProfitabilityResult
    bridge_version: str
    result_digest: str


class AdmittedProfitabilityEngine:
    def __init__(self, engine: ReconciledProfitabilityEngine | None = None) -> None:
        self._engine = engine or ReconciledProfitabilityEngine()

    def compute(
        self,
        *,
        admission: CalculationAdmissionResult,
        request: ProfitabilityComputationRequest,
        facts: tuple[AcquiredProfitabilityFact, ...],
        allocations: tuple[AllocatedProfitabilityCost, ...],
    ) -> AdmittedProfitabilityResult:
        if admission.state is not AdmissionState.ADMITTED:
            raise ProfitabilityAdmissionError(
                "profitability calculation requires admitted measurement evidence"
            )
        if admission.rejection_reasons or admission.blocking_components:
            raise ProfitabilityAdmissionError(
                "admitted measurement evidence cannot retain blockers"
            )
        computation = self._engine.compute(request, facts, allocations)
        payload = {
            "bridge_version": PROFITABILITY_ADMISSION_BRIDGE_VERSION,
            "admission_id": admission.admission_id,
            "admission_digest": admission.result_digest,
            "package_id": admission.package_id,
            "package_digest": admission.package_digest,
            "computation_digest": computation.digest,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return AdmittedProfitabilityResult(
            admission_id=admission.admission_id,
            admission_digest=admission.result_digest,
            package_id=admission.package_id,
            package_digest=admission.package_digest,
            computation=computation,
            bridge_version=PROFITABILITY_ADMISSION_BRIDGE_VERSION,
            result_digest=digest,
        )

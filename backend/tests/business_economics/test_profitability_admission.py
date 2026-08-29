from unittest.mock import Mock

import pytest

from app.business_economics.measurement_admission import (
    AdmissionState,
    CalculationAdmissionResult,
)
from app.business_economics.profitability_admission import (
    AdmittedProfitabilityEngine,
    ProfitabilityAdmissionError,
)


def _admission(state: AdmissionState) -> CalculationAdmissionResult:
    admitted = state is AdmissionState.ADMITTED
    return CalculationAdmissionResult(
        admission_id="eco-calculation-admission:" + "a" * 64,
        result_digest="a" * 64,
        admission_version="eco.measurement.admission.v1",
        package_id="eco-measurement-package:" + "b" * 64,
        package_digest="b" * 64,
        state=state,
        rejection_reasons=() if admitted else ("measurement_gate_partial",),
        blocking_components=(),
        unresolved_policy_ids=(),
        authority_limitations=(),
        explanation_facts=(f"admission={state.value}",),
    )


def test_rejected_measurement_never_reaches_profitability_engine() -> None:
    engine = Mock()
    bridge = AdmittedProfitabilityEngine(engine)

    with pytest.raises(ProfitabilityAdmissionError):
        bridge.compute(
            admission=_admission(AdmissionState.REJECTED_PARTIAL),
            request=Mock(),
            facts=(),
            allocations=(),
        )

    engine.compute.assert_not_called()


def test_admitted_result_is_bound_to_package_and_computation_digests() -> None:
    computation = Mock(digest="c" * 64)
    engine = Mock()
    engine.compute.return_value = computation
    request = Mock()
    result = AdmittedProfitabilityEngine(engine).compute(
        admission=_admission(AdmissionState.ADMITTED),
        request=request,
        facts=(),
        allocations=(),
    )

    engine.compute.assert_called_once_with(request, (), ())
    assert result.package_digest == "b" * 64
    assert result.computation is computation
    assert len(result.result_digest) == 64

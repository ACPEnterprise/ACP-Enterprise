from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from app.business_economics.operational_efficiency_diagnostics import (
    DIAGNOSTICS_VERSION,
    DiagnosticEvidenceInput,
    DiagnosticKind,
    DiagnosticState,
    build_operational_efficiency_diagnostics,
    operational_efficiency_diagnostics_contract,
)
from app.operational_measurement.labor_evidence import (
    EmployeeJobLink,
    IntervalKind,
    LaborInterval,
    ProvenanceRef,
    compose_labor_evidence,
)
from app.operational_measurement.productive_hour_readiness import (
    build_productive_hour_readiness,
)

START = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)


def _packet():
    company, branch, employee, job, appointment = (uuid4() for _ in range(5))
    ref = ProvenanceRef("accepted_time", "time-1", "v1", "d" * 64)
    labor = compose_labor_evidence(
        company_id=company,
        links=(EmployeeJobLink(company, branch, employee, job, appointment, ref),),
        intervals=(
            LaborInterval(
                company,
                None,
                employee,
                IntervalKind.PAID,
                START,
                START + timedelta(hours=8),
                ref,
            ),
            LaborInterval(
                company,
                branch,
                employee,
                IntervalKind.WORKED,
                START,
                START + timedelta(hours=5),
                ref,
                job,
                appointment,
            ),
            LaborInterval(
                company,
                branch,
                employee,
                IntervalKind.PRODUCTIVE,
                START,
                START + timedelta(hours=4),
                ref,
                job,
                appointment,
            ),
        ),
    )
    return build_productive_hour_readiness(labor), company, branch, employee, job


def _callback(company, employee, job, *, digest="b" * 64):
    return DiagnosticEvidenceInput(
        "callback-1",
        DiagnosticKind.CALLBACK_REWORK,
        company,
        None,
        employee,
        job,
        "2026-09",
        "accepted_callback_relationship",
        DiagnosticState.AVAILABLE,
        Decimal(1),
        "count",
        START,
        "a" * 64,
        digest,
        ("Relationship only; responsibility is not inferred.",),
    )


def test_diagnostics_expose_components_without_thresholds_or_actions() -> None:
    packet, company, _, employee, job = _packet()
    result = build_operational_efficiency_diagnostics(
        packet,
        reconciliation_key="2026-09",
        evidence=(_callback(company, employee, job),),
    )
    assert result.contract_version == DIAGNOSTICS_VERSION
    utilization = next(
        x for x in result.diagnostics if x.kind is DiagnosticKind.LOW_UTILIZATION
    )
    assert utilization.state is DiagnosticState.AVAILABLE
    assert ("PAID_MINUTES", "480", "AVAILABLE") in utilization.observed_components
    callback = next(
        x for x in result.diagnostics if x.kind is DiagnosticKind.CALLBACK_REWORK
    )
    assert callback.state is DiagnosticState.AVAILABLE
    conversion = next(
        x for x in result.diagnostics if x.kind is DiagnosticKind.LOW_CONVERSION
    )
    assert conversion.state is DiagnosticState.ABSENT
    assert result.causal_conclusion is None
    assert result.employment_action is None
    assert result.recommendation is None
    assert operational_efficiency_diagnostics_contract()["mutation_authority"] == "none"


def test_foreign_scope_period_duplicates_and_conflicts_fail_closed() -> None:
    packet, company, _, employee, job = _packet()
    item = _callback(company, employee, job)
    foreign = _callback(uuid4(), employee, job)
    with pytest.raises(ValueError, match="foreign Company"):
        build_operational_efficiency_diagnostics(
            packet, reconciliation_key="2026-09", evidence=(foreign,)
        )
    wrong_period = _callback(company, employee, job)
    object.__setattr__(wrong_period, "reconciliation_key", "2026-10")
    with pytest.raises(ValueError, match="mixed diagnostic"):
        build_operational_efficiency_diagnostics(
            packet, reconciliation_key="2026-09", evidence=(wrong_period,)
        )
    duplicate = _callback(company, employee, job)
    with pytest.raises(ValueError, match="duplicate diagnostic"):
        build_operational_efficiency_diagnostics(
            packet, reconciliation_key="2026-09", evidence=(item, duplicate)
        )


def test_same_subject_disagreement_is_conflicting_not_causal() -> None:
    packet, company, _, employee, job = _packet()
    first = _callback(company, employee, job)
    second = _callback(company, employee, job, digest="c" * 64)
    object.__setattr__(second, "evidence_id", "callback-2")
    result = build_operational_efficiency_diagnostics(
        packet, reconciliation_key="2026-09", evidence=(first, second)
    )
    callback = next(
        x for x in result.diagnostics if x.kind is DiagnosticKind.CALLBACK_REWORK
    )
    assert callback.state is DiagnosticState.CONFLICTING
    assert result.causal_conclusion is None

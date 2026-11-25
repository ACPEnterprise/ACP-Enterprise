from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from development_factory.failure_injection import (
    FailureInjectionError,
    FailureResult,
    FailureScenario,
    build_report,
    qualify_failure,
    write_report,
)


class InjectedFailure(RuntimeError):
    pass


CATEGORIES = {
    "credential_expiry": "credentials",
    "health_check_failure": "health",
    "migration_failure": "migration",
    "partial_execution": "partial_execution",
    "queue_discovery_failure": "coordination",
}


def scenario_result(identifier: str, *, recover_on: int = 1) -> FailureResult:
    scenario = FailureScenario(identifier, CATEGORIES[identifier], 3)

    def fail() -> None:
        raise InjectedFailure(
            "token=synthetic-secret database_url=postgresql://user:pass@host/db"
        )

    return qualify_failure(
        scenario,
        action=fail,
        expected_errors=(InjectedFailure,),
        recover=lambda attempt: attempt >= recover_on,
    )


def test_complete_failure_matrix_is_truthful_redacted_and_sealed(
    tmp_path: Path,
) -> None:
    results = [scenario_result(identifier) for identifier in CATEGORIES]

    report = build_report("a" * 40, results)
    path = tmp_path / "failure-report.json"
    write_report(path, report)

    serialized = path.read_text(encoding="utf-8")
    assert report["result"] == "PASS"
    assert report["deployment_authorized"] is False
    assert "synthetic-secret" not in serialized
    assert "user:pass" not in serialized
    assert "[REDACTED]" in serialized
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_recovery_retries_are_bounded() -> None:
    recovered = scenario_result("queue_discovery_failure", recover_on=3)
    exhausted = scenario_result("health_check_failure", recover_on=4)

    assert recovered.status == "PASS"
    assert recovered.recovery_attempts == 3
    assert exhausted.status == "FAIL"
    assert exhausted.recovery_attempts == 3
    assert exhausted.reason == "recovery retry budget exhausted"


def test_false_pass_and_unexpected_failure_type_are_never_accepted() -> None:
    scenario = FailureScenario("migration_failure", "migration", 1)
    false_pass = qualify_failure(
        scenario,
        action=lambda: None,
        expected_errors=(InjectedFailure,),
        recover=lambda _attempt: True,
    )

    def wrong_failure() -> None:
        raise OSError("unexpected")

    unexpected = qualify_failure(
        scenario,
        action=wrong_failure,
        expected_errors=(InjectedFailure,),
        recover=lambda _attempt: True,
    )

    assert false_pass.status == "FAIL"
    assert false_pass.failure_observed is False
    assert unexpected.status == "FAIL"
    assert unexpected.failure_type == "OSError"


def test_report_fails_for_missing_duplicate_or_failed_scenario() -> None:
    results = [scenario_result(identifier) for identifier in CATEGORIES]
    with pytest.raises(FailureInjectionError, match="incomplete"):
        build_report("a" * 40, results[:-1])
    with pytest.raises(FailureInjectionError, match="incomplete"):
        build_report("a" * 40, [*results, results[0]])

    failed = FailureResult(
        **{
            **results[0].__dict__,
            "status": "FAIL",
            "recovery_verified": False,
        }
    )
    report = build_report("a" * 40, [failed, *results[1:]])
    assert report["result"] == "FAIL"


def test_tampered_or_reused_evidence_path_is_rejected(tmp_path: Path) -> None:
    report = build_report(
        "a" * 40, [scenario_result(identifier) for identifier in CATEGORIES]
    )
    path = tmp_path / "report.json"
    write_report(path, report)
    with pytest.raises(FailureInjectionError, match="overwrite"):
        write_report(path, report)

    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["result"] = "FAIL"
    with pytest.raises(FailureInjectionError, match="digest"):
        write_report(tmp_path / "tampered.json", tampered)

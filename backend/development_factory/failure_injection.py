from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

from development_factory.reports import redact

CONTRACT: Final = "development-factory.failure-injection-report/v1"
REQUIRED_SCENARIOS: Final = (
    "credential_expiry",
    "health_check_failure",
    "migration_failure",
    "partial_execution",
    "queue_discovery_failure",
)
SHA40: Final = re.compile(r"[0-9a-f]{40}")


class FailureInjectionError(ValueError):
    """A fail-closed failure-injection qualification error."""


@dataclass(frozen=True)
class FailureScenario:
    id: str
    category: str
    max_recovery_attempts: int
    recovery_required: bool = True

    def validate(self) -> None:
        if self.id not in REQUIRED_SCENARIOS:
            raise FailureInjectionError("failure scenario ID is not approved")
        if self.category not in {
            "coordination",
            "credentials",
            "health",
            "migration",
            "partial_execution",
        }:
            raise FailureInjectionError("failure scenario category is invalid")
        if not 1 <= self.max_recovery_attempts <= 5:
            raise FailureInjectionError("recovery retry bound is invalid")


@dataclass(frozen=True)
class FailureResult:
    id: str
    category: str
    status: str
    failure_observed: bool
    failure_type: str | None
    recovery_attempts: int
    recovery_verified: bool
    reason: str


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def qualify_failure(
    scenario: FailureScenario,
    *,
    action: Callable[[], None],
    expected_errors: tuple[type[Exception], ...],
    recover: Callable[[int], bool],
) -> FailureResult:
    """Require one injected failure and bounded, explicit recovery evidence."""

    scenario.validate()
    if not expected_errors:
        raise FailureInjectionError("expected failure types are required")
    try:
        action()
    except expected_errors as error:
        failure_type = type(error).__name__
        safe_reason = redact(str(error))
    # This is the qualification boundary: unexpected injected exceptions must
    # become a truthful FAIL result rather than escaping as missing evidence.
    except Exception as error:  # noqa: BLE001
        return FailureResult(
            scenario.id,
            scenario.category,
            "FAIL",
            True,
            type(error).__name__,
            0,
            False,
            redact(f"unexpected failure type: {type(error).__name__}: {error}"),
        )
    else:
        return FailureResult(
            scenario.id,
            scenario.category,
            "FAIL",
            False,
            None,
            0,
            False,
            "injected failure unexpectedly passed",
        )

    if not scenario.recovery_required:
        return FailureResult(
            scenario.id,
            scenario.category,
            "PASS",
            True,
            failure_type,
            0,
            True,
            safe_reason,
        )
    for attempt in range(1, scenario.max_recovery_attempts + 1):
        try:
            recovered = recover(attempt)
        # Recovery adapters are untrusted test boundaries; preserve their
        # failure classification without allowing an unsealed partial report.
        except Exception as error:  # noqa: BLE001
            if attempt == scenario.max_recovery_attempts:
                return FailureResult(
                    scenario.id,
                    scenario.category,
                    "FAIL",
                    True,
                    failure_type,
                    attempt,
                    False,
                    redact(f"recovery failed: {type(error).__name__}: {error}"),
                )
            continue
        if recovered:
            return FailureResult(
                scenario.id,
                scenario.category,
                "PASS",
                True,
                failure_type,
                attempt,
                True,
                safe_reason,
            )
    return FailureResult(
        scenario.id,
        scenario.category,
        "FAIL",
        True,
        failure_type,
        scenario.max_recovery_attempts,
        False,
        "recovery retry budget exhausted",
    )


def build_report(
    candidate_sha: str, results: Sequence[FailureResult]
) -> dict[str, Any]:
    if not SHA40.fullmatch(candidate_sha):
        raise FailureInjectionError("candidate SHA is invalid")
    by_id = {result.id: result for result in results}
    if len(by_id) != len(results) or set(by_id) != set(REQUIRED_SCENARIOS):
        raise FailureInjectionError(
            "failure-injection matrix is incomplete or duplicated"
        )
    ordered = [by_id[scenario] for scenario in REQUIRED_SCENARIOS]
    passed = all(
        result.status == "PASS" and result.failure_observed and result.recovery_verified
        for result in ordered
    )
    unsigned: dict[str, Any] = {
        "candidate_sha": candidate_sha,
        "contract": CONTRACT,
        "deployment_authorized": False,
        "result": "PASS" if passed else "FAIL",
        "scenarios": [asdict(result) for result in ordered],
    }
    return {**unsigned, "digest": hashlib.sha256(canonical(unsigned)).hexdigest()}


def write_report(path: Path, report: dict[str, Any]) -> None:
    if (
        report.get("contract") != CONTRACT
        or report.get("deployment_authorized") is not False
    ):
        raise FailureInjectionError("failure-injection report contract is invalid")
    if (
        report.get("digest")
        != hashlib.sha256(
            canonical({key: value for key, value in report.items() if key != "digest"})
        ).hexdigest()
    ):
        raise FailureInjectionError("failure-injection report digest is invalid")
    path = path.resolve()
    if not path.parent.exists():
        path.parent.mkdir(mode=0o700, parents=True)
    if stat.S_IMODE(path.parent.stat().st_mode) & 0o077:
        raise FailureInjectionError("failure evidence directory is not private")
    if path.exists():
        raise FailureInjectionError("refusing to overwrite failure evidence")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)

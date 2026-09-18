from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

import pytest


def _module():
    path = Path(__file__).parents[3] / "scripts" / "enterprise-release-qualify"
    loader = importlib.machinery.SourceFileLoader(
        "enterprise_release_qualify", str(path)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


def test_release_catalog_covers_required_gates() -> None:
    module = _module()
    keys = {check.key for check in module.checks()}
    assert {
        "repository_cleanliness",
        "backend_dependencies",
        "backend_dependency_pins",
        "backend_vulnerabilities",
        "frontend_dependencies",
        "frontend_vulnerabilities",
        "mobile_dependencies",
        "mobile_vulnerabilities",
        "backend_lint",
        "backend_types",
        "backend_tests",
        "frontend_lint",
        "frontend_types",
        "frontend_tests",
        "frontend_build",
        "mobile_lint",
        "mobile_types",
        "mobile_tests",
        "mobile_configuration",
        "migration_heads",
        "migration_rehearsal",
        "api_health",
        "authentication_smoke",
        "authorization_smoke",
        "critical_crud",
        "background_services",
        "postgres_health",
        "redis_health",
        "preview_configuration",
        "secret_custody",
        "release_revision",
        "rollback_readiness",
        "postdeploy_routes",
    } <= keys


def test_every_executed_profile_is_bound_to_clean_candidate_provenance() -> None:
    module = _module()
    by_key = {check.key: check for check in module.checks()}
    expected = {"local", "database", "preview", "postdeploy", "commissioning"}

    for key in ("repository_cleanliness", "repository_provenance", "release_revision"):
        assert set(by_key[key].profiles) == expected


def test_status_vocabulary_is_closed() -> None:
    module = _module()
    assert module.STATUSES == {
        "PASS",
        "FAIL",
        "BLOCKED",
        "NOT APPLICABLE",
        "NOT YET EXECUTED",
    }


def result(module, status: str):
    return module.Result(
        "check",
        "Check",
        status,
        None,
        "expected",
        None,
        None,
        None,
        None,
        None,
        None,
    )


def test_executed_evidence_is_private_and_digest_bound(tmp_path: Path) -> None:
    module = _module()
    artifact = tmp_path / "evidence.log"
    check = module.Check(
        "evidence",
        "Evidence",
        ("local",),
        (sys.executable, "-c", "print('qualified')"),
        "qualified",
    )

    observed = module.run_command(check, tmp_path, artifact, "a" * 40)

    assert observed.status == "PASS"
    assert observed.artifact_sha256 == module.hashlib.sha256(
        artifact.read_bytes()
    ).hexdigest()
    assert artifact.stat().st_mode & 0o777 == 0o600


def test_existing_evidence_is_never_overwritten(tmp_path: Path) -> None:
    module = _module()
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    sealed = evidence / "qualification-packet.json"
    sealed.write_text('{"sealed":true}\n', encoding="utf-8")

    with pytest.raises(SystemExit, match="must be empty"):
        module.prepare_evidence_directory(evidence)

    assert sealed.read_text(encoding="utf-8") == '{"sealed":true}\n'


def test_evidence_directory_and_artifacts_are_private_and_exclusive(
    tmp_path: Path,
) -> None:
    module = _module()
    evidence = tmp_path / "nested" / "evidence"
    module.prepare_evidence_directory(evidence)
    artifact = evidence / "check.log"
    module.write_private_artifact(artifact, "first\n")

    assert evidence.stat().st_mode & 0o777 == 0o700
    assert artifact.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        module.write_private_artifact(artifact, "replacement\n")
    assert artifact.read_text(encoding="utf-8") == "first\n"


@pytest.mark.parametrize(
    ("check_key", "output", "reason"),
    (
        ("frontend_tests", "stderr | route test\n", "test suite emitted stderr"),
        (
            "mobile_tests",
            "The current testing environment is not configured to support act(...)\n",
            "React updates escaped act",
        ),
        ("frontend_tests", "Warning: unsafe update\n", "runtime warning"),
        ("mobile_tests", "  console.warn unexpected\n", "console output"),
    ),
)
def test_ui_test_warnings_fail_closed(
    check_key: str, output: str, reason: str
) -> None:
    module = _module()

    assert reason in module.test_output_warning(check_key, output)


def test_clean_ui_and_backend_output_is_not_misclassified() -> None:
    module = _module()

    assert module.test_output_warning("frontend_tests", "550 passed\n") is None
    assert module.test_output_warning("backend_tests", "Warning: recorded\n") is None


@pytest.mark.parametrize("status", ["FAIL", "BLOCKED"])
def test_incomplete_executed_qualification_fails_closed(status: str) -> None:
    module = _module()
    assert (
        module.qualification_decision([result(module, status)], executed=True) == status
    )


def test_executed_profile_can_pass_with_out_of_scope_checks_recorded() -> None:
    module = _module()
    results = [
        result(module, "PASS"),
        result(module, "NOT YET EXECUTED"),
        result(module, "NOT APPLICABLE"),
    ]
    assert module.qualification_decision(results, executed=True) == "PASS"


def test_plan_without_execution_never_claims_pass() -> None:
    module = _module()
    assert (
        module.qualification_decision(
            [result(module, "NOT YET EXECUTED")], executed=False
        )
        == "NOT YET EXECUTED"
    )


def test_rollback_receipts_must_match_authority_digests(tmp_path: Path) -> None:
    module = _module()
    backup = tmp_path / "backup.json"
    restore = tmp_path / "restore.json"
    backup.write_text('{"backup":"complete"}', encoding="utf-8")
    restore.write_text('{"restore":"verified"}', encoding="utf-8")
    backup_digest = module.receipt_digest(backup)
    restore_digest = module.receipt_digest(restore)

    assert module.rollback_readiness(backup, restore, None, None)[0] == "BLOCKED"
    assert (
        module.rollback_readiness(backup, restore, "0" * 64, restore_digest)[0]
        == "FAIL"
    )
    assert (
        module.rollback_readiness(backup, restore, backup_digest, restore_digest)[0]
        == "PASS"
    )

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
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
        "qualification_configuration",
        "mutation_registry",
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
        "tenant_isolation",
        "critical_crud",
        "background_services",
        "postgres_health",
        "redis_health",
        "database_security",
        "preview_configuration",
        "secret_custody",
        "release_revision",
        "rollback_readiness",
        "preview_approval",
        "postdeploy_routes",
        "protected_schema",
        "protected_release_metadata",
    } <= keys


def test_backend_gate_owns_a_disposable_database_lifecycle() -> None:
    module = _module()
    backend = next(check for check in module.checks() if check.key == "backend_tests")

    assert backend.command is not None
    assert backend.command[0] == "scripts/qualify-backend-tests"
    assert backend.command[1] == "--python"
    assert backend.command[-2:] == ("-ra", "backend/tests")
    assert backend.mutation == "disposable_database"
    assert "docker" in backend.required_tools


def test_every_executed_profile_is_bound_to_clean_candidate_provenance() -> None:
    module = _module()
    by_key = {check.key: check for check in module.checks()}
    expected = {
        "local",
        "database",
        "presigning",
        "preview",
        "postdeploy",
        "commissioning",
    }

    for key in ("repository_cleanliness", "repository_provenance", "release_revision"):
        assert set(by_key[key].profiles) == expected


def test_protected_check_dispatch_is_explicit_and_service_specific() -> None:
    module = _module()

    assert module.PROTECTED_RUNTIME_SERVICES == {
        "api_health": "backend",
        "database_security": "database-security",
        "postgres_health": "postgres",
        "redis_health": "redis",
        "authentication_smoke": "authentication",
        "authorization_smoke": "authorization",
        "tenant_isolation": "tenant-isolation",
        "background_services": "background-services",
        "postdeploy_routes": "routes",
        "protected_schema": "schema",
        "protected_release_metadata": "release-metadata",
    }


def test_independent_review_is_a_pre_signing_gate_without_approval() -> None:
    module = _module()
    review = next(
        check for check in module.checks() if check.key == "independent_review"
    )
    approval = next(
        check for check in module.checks() if check.key == "preview_approval"
    )

    assert review.profiles == ("presigning", "preview")
    assert approval.profiles == ("preview",)
    assert review.command is None
    assert approval.command is None


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
    assert (
        observed.artifact_sha256
        == module.hashlib.sha256(artifact.read_bytes()).hexdigest()
    )
    assert artifact.stat().st_mode & 0o777 == 0o600


def test_migration_head_check_requires_release_ready_canonical_lineage(
    tmp_path: Path,
) -> None:
    module = _module()
    valid_lineage_command = "; ".join(
        (
            "import json",
            "print(json.dumps({'release_ready': True, 'roots': ['r'], "
            + "'heads': ['h'], 'risks': []}))",
        )
    )
    check = module.Check(
        "migration_heads",
        "Exactly one Alembic head",
        ("local",),
        (
            sys.executable,
            "-c",
            valid_lineage_command,
        ),
        "release ready",
    )

    passed = module.run_command(check, tmp_path, tmp_path / "pass.log", "a" * 40)
    assert passed.status == "PASS"

    invalid = module.Check(
        "migration_heads",
        "Exactly one Alembic head",
        ("local",),
        (sys.executable, "-c", "print('not-json')"),
        "release ready",
    )
    failed = module.run_command(
        check=invalid, root=tmp_path, artifact=tmp_path / "fail.log", candidate="a" * 40
    )
    assert failed.status == "FAIL"
    assert failed.reason == "canonical migration lineage is not release-ready"


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
def test_ui_test_warnings_fail_closed(check_key: str, output: str, reason: str) -> None:
    module = _module()

    assert reason in module.test_output_warning(check_key, output)


def test_clean_ui_and_backend_output_is_not_misclassified() -> None:
    module = _module()

    assert module.test_output_warning("frontend_tests", "550 passed\n") is None
    assert (
        module.test_output_warning("backend_tests", "Warning: recorded\n")
        == "test suite emitted a runtime warning"
    )


@pytest.mark.parametrize("status", ["FAIL", "BLOCKED"])
def test_incomplete_executed_qualification_fails_closed(status: str) -> None:
    module = _module()
    assert (
        module.qualification_decision([result(module, status)], executed=True) == status
    )


def test_executed_profile_cannot_pass_with_out_of_scope_checks_unexecuted() -> None:
    module = _module()
    results = [
        result(module, "PASS"),
        result(module, "NOT YET EXECUTED"),
        result(module, "NOT APPLICABLE"),
    ]
    assert module.qualification_decision(results, executed=True) == "NOT YET EXECUTED"


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


def test_missing_tool_is_blocked_without_starting_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    check = module.Check(
        "missing",
        "Missing tool",
        ("local",),
        ("tool-that-does-not-exist",),
        "available",
        ("tool-that-does-not-exist",),
    )
    monkeypatch.setattr(module, "tool_available", lambda _tool: False)

    observed = module.run_command(check, tmp_path, tmp_path / "missing.log", "a" * 40)

    assert observed.status == "BLOCKED"
    assert observed.exit_code is None
    assert observed.artifact is None


def test_subprocess_failure_is_captured_with_exit_code_and_duration(
    tmp_path: Path,
) -> None:
    module = _module()
    check = module.Check(
        "failure",
        "Failure",
        ("local",),
        (sys.executable, "-c", "raise SystemExit(7)"),
        "success",
        (sys.executable,),
    )

    observed = module.run_command(check, tmp_path, tmp_path / "failure.log", "a" * 40)

    assert observed.status == "FAIL"
    assert observed.exit_code == 7
    assert observed.duration_seconds is not None
    assert observed.duration_seconds >= 0
    assert observed.failed_count == 0


def test_candidate_provenance_mismatch_fails_closed(tmp_path: Path) -> None:
    module = _module()
    check = module.Check(
        "repository_provenance",
        "Repository provenance",
        ("local",),
        (sys.executable, "-c", "print('b' * 40)"),
        "candidate",
        (sys.executable,),
    )

    observed = module.run_command(
        check, tmp_path, tmp_path / "provenance.log", "a" * 40
    )

    assert observed.status == "FAIL"
    assert observed.reason == "HEAD does not equal candidate SHA"


def test_application_and_tooling_provenance_are_independent(tmp_path: Path) -> None:
    module = _module()
    check = module.Check(
        "repository_provenance",
        "Repository provenance",
        ("local",),
        (sys.executable, "-c", "print('b' * 40)"),
        "tooling HEAD",
        (sys.executable,),
    )

    observed = module.run_command(
        check,
        tmp_path,
        tmp_path / "provenance.log",
        "a" * 40,
        tooling_sha="b" * 40,
    )

    assert observed.status == "PASS"


def test_captured_output_redacts_environment_assignments_and_url_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    secret = "qualification-secret-value"
    monkeypatch.setenv("QUALIFICATION_API_TOKEN", secret)
    payload = (
        f"QUALIFICATION_API_TOKEN={secret} "
        "DATABASE_URL=postgresql://user:database-password@db/name"
    )
    check = module.Check(
        "redaction",
        "Redaction",
        ("local",),
        (sys.executable, "-c", f"print({payload!r})"),
        "redacted",
        (sys.executable,),
    )
    artifact = tmp_path / "redaction.log"

    observed = module.run_command(check, tmp_path, artifact, "a" * 40)
    captured = artifact.read_text(encoding="utf-8")

    assert observed.status == "PASS"
    assert secret not in captured
    assert "database-password" not in captured
    assert captured.count("[REDACTED]") >= 2


def _valid_packet(module, root: Path, evidence: Path) -> dict[str, object]:
    artifact = evidence / "check.log"
    module.write_private_artifact(artifact, "qualified\n")
    item = module.Result(
        "check",
        "Check",
        "PASS",
        "command",
        "success",
        0,
        0.01,
        artifact.name,
        module.hashlib.sha256(artifact.read_bytes()).hexdigest(),
        None,
        0,
        0,
        (),
    )
    packet: dict[str, object] = {
        "contract": module.CONTRACT,
        "candidate_sha": "a" * 40,
        "application_sha": "a" * 40,
        "tooling_sha": "a" * 40,
        "protected_baseline_sha": "a" * 40,
        "observed_head": "a" * 40,
        "profile": "local",
        "executed": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "preview_revision": "NOT YET RECORDED",
        "preview_url": "NOT YET RECORDED",
        "results": [module.asdict(item)],
        "status_counts": {
            status: int(status == "PASS") for status in sorted(module.STATUSES)
        },
        "rollback_receipts": {},
        "schema": {
            "path": str(module.SCHEMA_PATH),
            "sha256": module.hashlib.sha256(
                (root / module.SCHEMA_PATH).read_bytes()
            ).hexdigest(),
        },
        "release_decision": "PASS",
        "deployment_authorized": False,
    }
    packet["digest"] = module.packet_digest(packet)
    return packet


def test_packet_is_schema_validated_digest_bound_and_sealed(tmp_path: Path) -> None:
    module = _module()
    root = Path(__file__).parents[3]
    evidence = tmp_path / "evidence"
    module.prepare_evidence_directory(evidence)
    packet = _valid_packet(module, root, evidence)
    module.validate_packet(packet, root)
    module.write_private_artifact(
        evidence / "qualification-packet.json",
        json.dumps(packet, indent=2, sort_keys=True) + "\n",
    )

    seal = module.seal_evidence(evidence, packet)
    verified = module.verify_evidence_seal(evidence, root)

    assert verified["digest"] == seal["digest"]
    assert (evidence / "evidence-seal.json").stat().st_mode & 0o777 == 0o600
    assert module.packet_digest(packet) == packet["digest"]

    (evidence / "check.log").chmod(0o600)
    (evidence / "check.log").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        module.verify_evidence_seal(evidence, root)


def test_database_runner_preserves_failure_and_always_cleans_up(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[3]
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$DOCKER_LOG"\n'
        'case " $* " in\n'
        '  *" down "*) touch "$DOCKER_DOWN_MARKER"; '
        'exit "${FAKE_DOWN_STATUS:-0}" ;;\n'
        '  *" up "*) exit "${FAKE_UP_STATUS:-0}" ;;\n'
        '  *" SHOW server_version_num"*) printf "160000\\n" ;;\n'
        '  *" SHOW server_encoding"*) printf "UTF8\\n" ;;\n'
        '  *"SELECT version_num FROM alembic_version"*) printf "head1\\n" ;;\n'
        '  *"SELECT count(*) FROM pg_class"*) printf "0\\n" ;;\n'
        '  *" pg_dump "*) printf "synthetic-backup\\n" ;;\n'
        '  *"exec -T readiness python"*) printf "HEALTHY\\n" ;;\n'
        '  *" compose "*" ps -q "*) printf "container-1\\n" ;;\n'
        '  *" inspect container-1 "*) '
        'printf \'%s\\n\' \'[{"HostConfig":{"PortBindings":{}},'
        '"NetworkSettings":{"Ports":{}}}]\' ;;\n'
        '  *" network inspect "*) printf "true\\n" ;;\n'
        '  *" network ls "*) test -e "$DOCKER_DOWN_MARKER" || '
        'printf "network-1\\n" ;;\n'
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o700)
    log = tmp_path / "docker.log"
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DOCKER_LOG": str(log),
        "DOCKER_DOWN_MARKER": str(tmp_path / "down.marker"),
        "FAKE_UP_STATUS": "9",
    }

    failed = subprocess.run(
        (str(root / "scripts/qualify-release-database"),),
        cwd=tmp_path,
        env=environment,
        check=False,
    )

    assert failed.returncode == 9
    assert " down " in f" {log.read_text(encoding='utf-8')} "

    log.unlink()
    (tmp_path / "down.marker").unlink()
    environment.update({"FAKE_UP_STATUS": "0", "FAKE_DOWN_STATUS": "8"})
    cleanup_failed = subprocess.run(
        (str(root / "scripts/qualify-release-database"),),
        cwd=tmp_path,
        env=environment,
        check=False,
    )
    assert cleanup_failed.returncode == 70


def test_runner_supplies_import_root_without_shell_pythonpath(tmp_path: Path) -> None:
    module = _module()
    root = Path(__file__).parents[3]
    check = module.Check(
        "import_root",
        "Import root",
        ("local",),
        (
            sys.executable,
            "-c",
            (
                "from app.platform.idempotency.coverage import "
                "mutation_coverage_registry; "
                "print(len(mutation_coverage_registry.entries))"
            ),
        ),
        "import succeeds",
        (sys.executable,),
    )
    artifact = tmp_path / "import.log"

    observed = module.run_command(check, root, artifact, "a" * 40)

    assert observed.status == "PASS"
    assert int(artifact.read_text(encoding="utf-8")) > 0

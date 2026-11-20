from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path


def test_backend_harness_uses_release_qualification_postgres_image() -> None:
    root = Path(__file__).parents[3]
    compose = (root / "docker-compose.release-qualification.yml").read_text(
        encoding="utf-8"
    )
    harness = (root / "scripts/qualify-backend-tests").read_text(encoding="utf-8")
    pinned_image = next(
        line.strip().removeprefix("image: ")
        for line in compose.splitlines()
        if line.strip().startswith("image: postgres:16-alpine@sha256:")
    )

    assert pinned_image in harness


def _fake_tools(tmp_path: Path) -> tuple[Path, Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    python_log = tmp_path / "python.log"

    docker = fake_bin / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$DOCKER_LOG"\n'
        'case " $* " in\n'
        '  *" run --detach "*) printf "owned-postgres-container\\n" ;;\n'
        '  *" inspect --format "*".State.Health.Status"*) '
        'printf "healthy\\n" ;;\n'
        '  *" inspect --format "*"NetworkSettings.Ports"*) '
        'printf "127.0.0.1:55432\\n" ;;\n'
        '  *" SHOW server_version_num"*) printf "160011\\n" ;;\n'
        '  *" SHOW server_encoding"*) printf "UTF8\\n" ;;\n'
        '  *"SELECT count(*) FROM pg_class"*) printf "0\\n" ;;\n'
        '  *" ps -aq "*) test -e "$CONTAINER_REMOVED" || '
        'printf "owned-postgres-container\\n" ;;\n'
        '  *" volume ls "*) test -e "$VOLUME_REMOVED" || '
        'printf "owned-postgres-volume\\n" ;;\n'
        '  *" network ls "*) test -e "$NETWORK_REMOVED" || '
        'printf "owned-postgres-network\\n" ;;\n'
        '  *" rm -f owned-postgres-container "*) touch "$CONTAINER_REMOVED"; '
        'exit "${FAKE_CLEANUP_STATUS:-0}" ;;\n'
        '  *" volume rm owned-postgres-volume "*) touch "$VOLUME_REMOVED" ;;\n'
        '  *" network rm owned-postgres-network "*) touch "$NETWORK_REMOVED" ;;\n'
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o700)

    python = fake_bin / "python"
    python.write_text(
        "#!/bin/sh\n"
        'printf "%s|%s\\n" "$DATABASE_URL" "$*" >> "$PYTHON_LOG"\n'
        'case " $* " in\n'
        '  *" -c import socket;"*) printf "55432\\n"; exit 0 ;;\n'
        '  *" -m pytest "*) '
        'if test -n "${FAKE_PYTEST_HOLD_MARKER:-}"; then '
        'touch "$FAKE_PYTEST_HOLD_MARKER"; '
        "trap 'exit 143' TERM; while :; do sleep 1; done; fi; "
        'exit "${FAKE_PYTEST_STATUS:-0}" ;;\n'
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    python.chmod(0o700)
    return fake_bin, docker_log, python_log


def _run_harness(
    tmp_path: Path,
    *,
    pytest_status: str = "0",
    cleanup_status: str = "0",
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    root = Path(__file__).parents[3]
    fake_bin, docker_log, python_log = _fake_tools(tmp_path)
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DATABASE_URL": "postgresql+asyncpg://shared:unsafe@production.invalid/live",
        "DOCKER_LOG": str(docker_log),
        "PYTHON_LOG": str(python_log),
        "CONTAINER_REMOVED": str(tmp_path / "container-removed.marker"),
        "VOLUME_REMOVED": str(tmp_path / "volume-removed.marker"),
        "NETWORK_REMOVED": str(tmp_path / "network-removed.marker"),
        "FAKE_PYTEST_STATUS": pytest_status,
        "FAKE_CLEANUP_STATUS": cleanup_status,
    }
    completed = subprocess.run(
        (
            str(root / "scripts/qualify-backend-tests"),
            "--python",
            str(fake_bin / "python"),
            "-q",
            "backend/tests/payroll",
        ),
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed, docker_log, python_log


def test_backend_harness_replaces_caller_database_and_cleans_up(
    tmp_path: Path,
) -> None:
    completed, docker_log, python_log = _run_harness(tmp_path)

    assert completed.returncode == 0, completed.stderr
    invocations = python_log.read_text(encoding="utf-8")
    assert "production.invalid" not in invocations
    assert "@127.0.0.1:55432/release_qualification" in invocations
    assert "-m alembic upgrade head" in invocations
    assert "-m alembic current --check-heads" in invocations
    assert "-m alembic check" in invocations
    assert "-m pytest -q backend/tests/payroll" in invocations
    cleanup_log = docker_log.read_text(encoding="utf-8")
    assert "--health-cmd pg_isready -h 127.0.0.1" in cleanup_log
    assert "rm -f owned-postgres-container" in cleanup_log
    assert "volume rm owned-postgres-volume" in cleanup_log
    assert "network rm owned-postgres-network" in cleanup_log
    assert "BACKEND_TEST_DATABASE_CLEANUP=VERIFIED" in completed.stdout


def test_backend_harness_preserves_test_failure_and_still_cleans_up(
    tmp_path: Path,
) -> None:
    completed, docker_log, _ = _run_harness(tmp_path, pytest_status="9")

    assert completed.returncode == 9
    assert "rm -f owned-postgres-container" in docker_log.read_text(encoding="utf-8")


def test_backend_harness_fails_closed_when_cleanup_fails(tmp_path: Path) -> None:
    completed, _, _ = _run_harness(tmp_path, cleanup_status="8")

    assert completed.returncode == 70
    assert "cleanup failed" in completed.stderr


def test_backend_harness_term_cleans_up_and_exits_143(tmp_path: Path) -> None:
    root = Path(__file__).parents[3]
    fake_bin, docker_log, _ = _fake_tools(tmp_path)
    hold_marker = tmp_path / "pytest-holding.marker"
    cleanup_markers = {
        "CONTAINER_REMOVED": tmp_path / "container-removed.marker",
        "VOLUME_REMOVED": tmp_path / "volume-removed.marker",
        "NETWORK_REMOVED": tmp_path / "network-removed.marker",
    }
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "DATABASE_URL": "postgresql+asyncpg://shared:unsafe@production.invalid/live",
        "DOCKER_LOG": str(docker_log),
        "PYTHON_LOG": str(tmp_path / "python.log"),
        "FAKE_PYTEST_HOLD_MARKER": str(hold_marker),
        **{name: str(path) for name, path in cleanup_markers.items()},
    }
    process = subprocess.Popen(
        (
            str(root / "scripts/qualify-backend-tests"),
            "--python",
            str(fake_bin / "python"),
            "-q",
            "backend/tests/payroll",
        ),
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    deadline = time.monotonic() + 10
    while not hold_marker.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert hold_marker.exists(), "fake pytest did not reach its hold point"

    os.killpg(process.pid, signal.SIGTERM)
    stdout, stderr = process.communicate(timeout=10)

    assert process.returncode == 143, (stdout, stderr)
    assert all(path.exists() for path in cleanup_markers.values())
    cleanup_log = docker_log.read_text(encoding="utf-8")
    assert "rm -f owned-postgres-container" in cleanup_log
    assert "volume rm owned-postgres-volume" in cleanup_log
    assert "network rm owned-postgres-network" in cleanup_log

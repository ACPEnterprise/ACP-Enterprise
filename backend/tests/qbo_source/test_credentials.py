from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.qbo_source.credentials import (
    DevelopmentCredentialProvisioningError,
    provision_development_credentials,
)
from app.qbo_source.secrets import ProtectedSandboxSecretProvider

CLIENT_ID = "synthetic-development-client-id"
CLIENT_SECRET = "synthetic-development-client-secret"


def _source(path: Path, value: str) -> Path:
    path.write_text(f"{value}\n")
    path.chmod(0o600)
    return path


def _provision(tmp_path: Path):  # type: ignore[no-untyped-def]
    return provision_development_credentials(
        client_id_file=_source(tmp_path / "client-id", CLIENT_ID),
        client_secret_file=_source(tmp_path / "client-secret", CLIENT_SECRET),
        secret_root=tmp_path / "runtime" / "secrets",
        repository_root=tmp_path / "repository",
    )


def test_valid_legacy_pair_provisions_provider_document(tmp_path: Path) -> None:
    result = _provision(tmp_path)
    document = json.loads(result.target.read_text())

    assert result.status == "PROVISIONED"
    assert document == {
        "environment": "sandbox",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    assert result.target.stat().st_mode & 0o777 == 0o600
    assert result.target.parent.stat().st_mode & 0o777 == 0o700


@pytest.mark.asyncio
async def test_provisioned_document_loads_through_sandbox_provider(
    tmp_path: Path,
) -> None:
    result = _provision(tmp_path)
    provider = ProtectedSandboxSecretProvider(
        root=result.target.parent, repository_root=tmp_path / "repository"
    )

    credential = await provider.get_client_credential(provider.CLIENT_REFERENCE)

    assert credential.client_id == CLIENT_ID
    assert credential.client_secret == CLIENT_SECRET


def test_exact_replay_is_idempotent(tmp_path: Path) -> None:
    first = _provision(tmp_path)
    second = _provision(tmp_path)

    assert first.status == "PROVISIONED"
    assert second.status == "ALREADY_CURRENT"
    assert second.target == first.target


def test_conflicting_target_rejects(tmp_path: Path) -> None:
    _provision(tmp_path)
    client_id = _source(tmp_path / "client-id", CLIENT_ID)
    client_secret = _source(tmp_path / "client-secret", "different-development-secret")

    with pytest.raises(DevelopmentCredentialProvisioningError) as raised:
        provision_development_credentials(
            client_id_file=client_id,
            client_secret_file=client_secret,
            secret_root=tmp_path / "runtime" / "secrets",
            repository_root=tmp_path / "repository",
        )

    assert raised.value.code == "credential_target_conflict"


@pytest.mark.parametrize("mode", [0o604, 0o640, 0o644])
def test_unsafe_source_permissions_reject(tmp_path: Path, mode: int) -> None:
    client_id = _source(tmp_path / "client-id", CLIENT_ID)
    client_id.chmod(mode)

    with pytest.raises(DevelopmentCredentialProvisioningError) as raised:
        provision_development_credentials(
            client_id_file=client_id,
            client_secret_file=_source(tmp_path / "client-secret", CLIENT_SECRET),
            secret_root=tmp_path / "runtime" / "secrets",
            repository_root=tmp_path / "repository",
        )

    assert raised.value.code == "client_id_permissions_invalid"


def test_symlink_source_rejects(tmp_path: Path) -> None:
    actual = _source(tmp_path / "actual-client-id", CLIENT_ID)
    linked = tmp_path / "client-id"
    linked.symlink_to(actual)

    with pytest.raises(DevelopmentCredentialProvisioningError) as raised:
        provision_development_credentials(
            client_id_file=linked,
            client_secret_file=_source(tmp_path / "client-secret", CLIENT_SECRET),
            secret_root=tmp_path / "runtime" / "secrets",
            repository_root=tmp_path / "repository",
        )

    assert raised.value.code == "client_id_source_invalid"


def test_source_or_target_inside_repository_rejects(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    client_id = _source(repository / "client-id", CLIENT_ID)
    client_secret = _source(tmp_path / "client-secret", CLIENT_SECRET)

    with pytest.raises(DevelopmentCredentialProvisioningError) as source_error:
        provision_development_credentials(
            client_id_file=client_id,
            client_secret_file=client_secret,
            secret_root=tmp_path / "runtime" / "secrets",
            repository_root=repository,
        )
    assert source_error.value.code == "credential_source_inside_repository"

    client_id = _source(tmp_path / "client-id", CLIENT_ID)
    with pytest.raises(DevelopmentCredentialProvisioningError) as target_error:
        provision_development_credentials(
            client_id_file=client_id,
            client_secret_file=client_secret,
            secret_root=repository / "secrets",
            repository_root=repository,
        )
    assert target_error.value.code == "credential_target_inside_repository"


@pytest.mark.parametrize("value", ["", "two\nvalues", " padded ", "bad\rvalue"])
def test_malformed_or_empty_source_rejects(tmp_path: Path, value: str) -> None:
    with pytest.raises(DevelopmentCredentialProvisioningError):
        provision_development_credentials(
            client_id_file=_source(tmp_path / "client-id", value),
            client_secret_file=_source(tmp_path / "client-secret", CLIENT_SECRET),
            secret_root=tmp_path / "runtime" / "secrets",
            repository_root=tmp_path / "repository",
        )


def test_cli_output_and_logs_do_not_expose_credentials(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client_id = _source(tmp_path / "client-id", CLIENT_ID)
    client_secret = _source(tmp_path / "client-secret", CLIENT_SECRET)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[2])

    with caplog.at_level(logging.DEBUG):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.qbo_source.credentials",
                "provision-development",
                "--client-id-file",
                str(client_id),
                "--client-secret-file",
                str(client_secret),
                "--secret-root",
                str(tmp_path / "runtime" / "secrets"),
                "--repository-root",
                str(tmp_path / "repository"),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    assert completed.returncode == 0
    assert json.loads(completed.stdout)["status"] == "PROVISIONED"
    combined = completed.stdout + completed.stderr + caplog.text
    assert CLIENT_ID not in combined
    assert CLIENT_SECRET not in combined


def test_production_target_is_not_supported_by_command() -> None:
    source = Path(__file__).parents[2] / "app" / "qbo_source" / "credentials.py"
    contents = source.read_text()

    assert "provision-production" not in contents
    assert '"environment": "sandbox"' in contents


def test_cli_rejects_production_command_without_secret_output(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[2])

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.qbo_source.credentials",
            "provision-production",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode != 0
    assert CLIENT_ID not in completed.stdout + completed.stderr
    assert CLIENT_SECRET not in completed.stdout + completed.stderr

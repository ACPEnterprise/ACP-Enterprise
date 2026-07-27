import base64
import stat
from pathlib import Path
from uuid import uuid4

import pytest

from app.worker_control.contracts import WorkerCapability
from app.worker_control.transport.crypto import decode_private_key, verify_signature
from app.worker_runtime.config import WorkerRuntimeConfig
from app.worker_runtime.provision import (
    Ed25519FileCredentialIssuer,
    ProvisioningConfig,
)


@pytest.mark.asyncio
async def test_file_issuer_writes_only_owner_readable_private_key(
    tmp_path: Path,
) -> None:
    path = tmp_path / "worker.key"
    metadata = await Ed25519FileCredentialIssuer(path).issue(
        identity_id=uuid4(), credential_version=1
    )

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    private_key = decode_private_key(path.read_text())
    message = b"challenge"
    signature = private_key.sign(message)
    assert verify_signature(
        public_key=metadata.verifier,
        signature=base64.urlsafe_b64encode(signature).rstrip(b"=").decode(),
        message=message,
    )
    assert metadata.verifier_algorithm == "ed25519"


def test_runtime_defaults_to_connectivity_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "worker.key"
    path.write_text("private")
    path.chmod(0o600)
    monkeypatch.setenv("ACP_WORKER_BASE_URL", "https://preview.example")
    monkeypatch.setenv("ACP_WORKER_ID", str(uuid4()))
    monkeypatch.setenv("ACP_WORKER_PRIVATE_KEY_FILE", str(path))
    monkeypatch.delenv("ACP_WORKER_CAPABILITIES", raising=False)

    config = WorkerRuntimeConfig.from_environment()

    assert config.capabilities == (WorkerCapability.CONNECTIVITY,)


def test_provisioning_configuration_rejects_relative_private_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACP_WORKER_COMPANY_CODE", "ACP")
    monkeypatch.setenv("ACP_WORKER_ADMINISTRATOR_EMAIL", "owner@example.com")
    monkeypatch.setenv("ACP_WORKER_PRIVATE_KEY_FILE", "worker.key")

    with pytest.raises(ValueError, match="invalid"):
        ProvisioningConfig.from_environment()

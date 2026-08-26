import asyncio
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from app.worker_control.contracts import (
    AuthenticatedWorkerContext,
    WorkerCapability,
    WorkerHealth,
)
from app.worker_control.transport.contracts import (
    AuthenticatedMessageEnvelope,
    HeartbeatMessage,
    TransportMessageKind,
    WorkerSession,
    WorkerSessionState,
)
from app.worker_control.transport.crypto import canonical_message, encode_signature
from app.worker_control.transport.http.dependencies import (
    Ed25519CredentialProofVerifier,
    Ed25519MessageProofVerifier,
)
from app.worker_runtime.client import Challenge, Session, WorkerRuntimeTransportError
from app.worker_runtime.config import WorkerRuntimeConfig
from app.worker_runtime.recovery import RecoveryRecord, WorkerRecoveryJournal
from app.worker_runtime.service import AuthenticatedWorkerRuntime, WorkerRuntimeState
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

NOW = datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc)


def public_key(private: Ed25519PrivateKey) -> str:
    raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.mark.asyncio
async def test_ed25519_challenge_and_message_proofs_fail_closed() -> None:
    private = Ed25519PrivateKey.generate()
    verifier = public_key(private)
    challenge = "bounded-one-time-challenge"
    credential = Ed25519CredentialProofVerifier()
    assert await credential.verify(
        challenge=challenge,
        response=encode_signature(private.sign(challenge.encode())),
        verifier=verifier,
        verifier_algorithm="ed25519",
    )
    assert not await credential.verify(
        challenge=challenge + "-altered",
        response=encode_signature(private.sign(challenge.encode())),
        verifier=verifier,
        verifier_algorithm="ed25519",
    )

    worker_id, session_id = uuid4(), uuid4()
    session = WorkerSession(
        session_id=session_id,
        context=AuthenticatedWorkerContext(
            company_id=uuid4(),
            worker_id=worker_id,
            provider_identifier="codex",
            authentication_subject="worker-identity:test",
            authenticated_at=NOW,
        ),
        worker_identity_id=uuid4(),
        credential_id=uuid4(),
        credential_version=1,
        capabilities=(WorkerCapability.ENGINEERING_EXECUTE,),
        key_version="1",
        state=WorkerSessionState.ACTIVE,
        established_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
        next_sequence=1,
    )
    unsigned = AuthenticatedMessageEnvelope(
        message_id=uuid4(),
        session_id=session_id,
        worker_id=worker_id,
        sequence_number=1,
        sent_at=NOW,
        kind=TransportMessageKind.HEARTBEAT,
        payload=HeartbeatMessage(WorkerHealth.HEALTHY),
        authentication_proof="",
        key_version="1",
    )
    signed = AuthenticatedMessageEnvelope(
        **{
            **unsigned.__dict__,
            "authentication_proof": encode_signature(
                private.sign(canonical_message(unsigned))
            ),
        }
    )
    messages = Ed25519MessageProofVerifier()
    assert await messages.verify_message(
        envelope=signed,
        session=session,
        verifier=verifier,
        verifier_algorithm="ed25519",
    )
    altered = AuthenticatedMessageEnvelope(**{**signed.__dict__, "sequence_number": 2})
    assert not await messages.verify_message(
        envelope=altered,
        session=session,
        verifier=verifier,
        verifier_algorithm="ed25519",
    )


class FakeClient:
    def __init__(self) -> None:
        self.private: Ed25519PrivateKey | None = None
        self.heartbeats: list[dict[str, object]] = []
        self.renewals: list[dict[str, object]] = []
        self.closed = False
        self.results: list[dict[str, object]] = []
        self.result_failures = 0
        self.result_attempts = 0

    async def challenge(self, worker_id):
        del worker_id
        return Challenge(uuid4(), "challenge", "1")

    async def establish(self, *, worker_id, challenge, proof, capabilities):
        del worker_id, capabilities
        assert self.private is not None
        self.private.public_key().verify(
            base64.urlsafe_b64decode(proof + "=" * (-len(proof) % 4)),
            challenge.challenge.encode(),
        )
        return Session(uuid4(), challenge.key_version, 1, NOW + timedelta(minutes=15))

    async def heartbeat(self, *, session_id, payload):
        assert str(session_id) == payload["session_id"]
        self.heartbeats.append(payload)

    async def renew_lease(self, *, session_id, payload):
        assert str(session_id) == payload["session_id"]
        self.renewals.append(payload)

    async def close(self):
        self.closed = True

    async def submit_controlled_result(self, *, session_id, payload):
        assert str(session_id) == payload["session_id"]
        self.result_attempts += 1
        if self.result_failures:
            self.result_failures -= 1
            raise WorkerRuntimeTransportError("temporary result transport failure")
        self.results.append(payload)


@pytest.mark.asyncio
async def test_runtime_establishes_heartbeats_and_renews_only_explicit_lease(
    tmp_path: Path,
) -> None:
    private = Ed25519PrivateKey.generate()
    client = FakeClient()
    client.private = private
    runtime = AuthenticatedWorkerRuntime(
        config=WorkerRuntimeConfig(
            base_url="https://worker.invalid",
            worker_id=uuid4(),
            private_key_file=Path("/not-read-by-injected-runtime"),
            capabilities=(WorkerCapability.ENGINEERING_EXECUTE,),
            workspace_root=tmp_path,
            state_directory=tmp_path / "state",
        ),
        client=client,  # type: ignore[arg-type]
        private_key=private,
        journal=WorkerRecoveryJournal(tmp_path / "state"),
    )

    connected = await runtime.establish()
    assert connected.state is WorkerRuntimeState.CONNECTED
    heartbeat = await runtime.heartbeat()
    assert heartbeat.next_sequence == 2
    assert len(client.heartbeats) == 1
    await runtime.renew_lease(lease_id=uuid4(), expected_version=1, lease_seconds=60)
    assert runtime.snapshot.next_sequence == 3
    assert len(client.renewals) == 1
    assert not hasattr(runtime, "execute")

    await runtime.close()
    assert runtime.snapshot.state is WorkerRuntimeState.CLOSED
    assert runtime.snapshot.session_id is None
    assert client.closed


@pytest.mark.asyncio
async def test_pending_result_is_redelivered_once_after_new_session(
    tmp_path: Path,
) -> None:
    private = Ed25519PrivateKey.generate()
    client = FakeClient()
    client.private = private
    journal = WorkerRecoveryJournal(tmp_path / "state")
    pending = RecoveryRecord(
        phase="pending_result",
        offer_id=uuid4(),
        lease_id=uuid4(),
        started_at=NOW,
        result={
            "outcome": "succeeded",
            "output": {"repository_mutated": False},
            "error_classification": None,
            "completed_at": NOW.isoformat(),
        },
    )
    journal.store(pending)
    runtime = AuthenticatedWorkerRuntime(
        config=WorkerRuntimeConfig(
            base_url="https://worker.invalid",
            worker_id=uuid4(),
            private_key_file=tmp_path / "unused.key",
            capabilities=(WorkerCapability.ENGINEERING_EXECUTE,),
            workspace_root=tmp_path,
            state_directory=tmp_path / "state",
        ),
        client=client,  # type: ignore[arg-type]
        private_key=private,
        journal=journal,
    )

    await runtime.establish()
    await runtime._deliver_pending_result(journal.load())  # type: ignore[arg-type]

    assert len(client.results) == 1
    assert journal.load() is None


@pytest.mark.asyncio
async def test_terminal_result_delivery_retries_bounded_transport_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private = Ed25519PrivateKey.generate()
    client = FakeClient()
    client.private = private
    client.result_failures = 2
    journal = WorkerRecoveryJournal(tmp_path / "state")
    pending = RecoveryRecord(
        phase="pending_result",
        offer_id=uuid4(),
        lease_id=uuid4(),
        started_at=NOW,
        result={
            "outcome": "succeeded",
            "output": {"repository_mutated": False},
            "error_classification": None,
            "completed_at": NOW.isoformat(),
        },
    )
    journal.store(pending)
    runtime = AuthenticatedWorkerRuntime(
        config=WorkerRuntimeConfig(
            base_url="https://worker.invalid",
            worker_id=uuid4(),
            private_key_file=tmp_path / "unused.key",
            capabilities=(WorkerCapability.ENGINEERING_EXECUTE,),
            workspace_root=tmp_path,
            state_directory=tmp_path / "state",
        ),
        client=client,  # type: ignore[arg-type]
        private_key=private,
        journal=journal,
    )

    async def no_delay(_: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_delay)
    await runtime.establish()
    await runtime._deliver_pending_result(pending)

    assert client.result_failures == 0
    assert client.result_attempts == 3
    assert len(client.results) == 1
    assert journal.load() is None
    assert runtime.snapshot.next_sequence == 2


@pytest.mark.asyncio
async def test_long_running_execution_heartbeat_and_lease_are_distinct_and_serialized(
    tmp_path: Path,
) -> None:
    private = Ed25519PrivateKey.generate()
    client = FakeClient()
    client.private = private
    runtime = AuthenticatedWorkerRuntime(
        config=WorkerRuntimeConfig(
            base_url="https://worker.invalid",
            worker_id=uuid4(),
            private_key_file=tmp_path / "unused.key",
            capabilities=(WorkerCapability.ENGINEERING_EXECUTE,),
            heartbeat_seconds=10,
            workspace_root=tmp_path,
            state_directory=tmp_path / "state",
        ),
        client=client,  # type: ignore[arg-type]
        private_key=private,
        journal=WorkerRecoveryJournal(tmp_path / "state"),
    )
    await runtime.establish()
    task = asyncio.create_task(
        runtime._maintain_execution_lease(
            lease_id=uuid4(),
            initial_version=7,
            renew_immediately=True,
        )
    )
    for _ in range(20):
        if client.renewals:
            break
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(client.heartbeats) == 1
    assert len(client.renewals) == 1
    assert client.heartbeats[0]["sequence_number"] == 1
    assert client.renewals[0]["sequence_number"] == 2
    assert client.renewals[0]["expected_lease_version"] == 7


def test_acquired_execution_survives_restart_as_reconciliation_truth(
    tmp_path: Path,
) -> None:
    journal = WorkerRecoveryJournal(tmp_path / "state")
    acquired = RecoveryRecord(
        phase="acquired",
        offer_id=uuid4(),
        lease_id=uuid4(),
        started_at=NOW,
    )
    journal.store(acquired)

    assert journal.load() == acquired
    assert (tmp_path / "state" / "runtime-state.json").stat().st_mode & 0o077 == 0


def test_private_key_file_must_be_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "worker.key"
    path.write_text("not-a-real-key", encoding="utf-8")
    path.chmod(0o644)
    config = WorkerRuntimeConfig(
        base_url="https://worker.invalid",
        worker_id=uuid4(),
        private_key_file=path,
        capabilities=(WorkerCapability.ENGINEERING_EXECUTE,),
    )
    with pytest.raises(PermissionError):
        config.read_private_key()

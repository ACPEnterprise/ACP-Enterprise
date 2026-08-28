import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

RecoveryPhase = Literal["acquired", "pending_result", "reconciliation_required"]


@dataclass(frozen=True)
class RecoveryRecord:
    phase: RecoveryPhase
    offer_id: UUID
    lease_id: UUID
    started_at: datetime
    result: dict[str, object] | None = None


class WorkerRecoveryJournal:
    """Owner-only durable truth for safe restart and result redelivery."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.path = directory / "runtime-state.json"
        self.health_path = directory / "health.json"

    def initialize(self) -> None:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.directory.stat().st_mode & 0o077:
            raise PermissionError("Worker state directory permissions must be 700.")

    def load(self) -> RecoveryRecord | None:
        self.initialize()
        if not self.path.exists():
            return None
        if self.path.stat().st_mode & 0o077:
            raise PermissionError("Worker recovery state permissions must be 600.")
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return RecoveryRecord(
            phase=payload["phase"],
            offer_id=UUID(payload["offer_id"]),
            lease_id=UUID(payload["lease_id"]),
            started_at=datetime.fromisoformat(payload["started_at"]),
            result=payload.get("result"),
        )

    def store(self, record: RecoveryRecord) -> None:
        self.initialize()
        payload = {
            **asdict(record),
            "offer_id": str(record.offer_id),
            "lease_id": str(record.lease_id),
            "started_at": record.started_at.isoformat(),
        }
        temporary = self.path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.path)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def digest(self) -> str | None:
        if not self.path.exists():
            return None
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def acknowledge(
        self,
        *,
        acknowledgement_id: UUID,
        expected_journal_digest: str,
        audit_digest: str,
        acknowledged_at: datetime,
        worker_id: UUID,
        command_id: UUID,
        execution_id: UUID,
        offer_id: UUID,
        lease_id: UUID,
    ) -> str:
        """Archive immutable local truth before releasing its active block."""
        record = self.load()
        if record is None or record.phase != "reconciliation_required":
            raise ValueError("Local recovery journal is not reconciliation-required.")
        if record.result is not None:
            raise ValueError("A pending provider result must use normal delivery.")
        if record.offer_id != offer_id or record.lease_id != lease_id:
            raise ValueError("Local recovery lineage does not match acknowledgement.")
        journal_bytes = self.path.read_bytes()
        journal_digest = hashlib.sha256(journal_bytes).hexdigest()
        if journal_digest != expected_journal_digest:
            raise ValueError(
                "Local recovery journal digest does not match acknowledgement."
            )
        history = self.directory / "recovery-history"
        history.mkdir(mode=0o700, parents=True, exist_ok=True)
        if history.stat().st_mode & 0o077:
            raise PermissionError("Worker recovery history permissions must be 700.")
        payload = {
            "acknowledgement_id": str(acknowledgement_id),
            "acknowledged_at": acknowledged_at.isoformat(),
            "audit_digest": audit_digest,
            "command_id": str(command_id),
            "execution_id": str(execution_id),
            "journal": json.loads(journal_bytes),
            "journal_digest": journal_digest,
            "lease_id": str(lease_id),
            "offer_id": str(offer_id),
            "worker_id": str(worker_id),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        archive_digest = hashlib.sha256(encoded).hexdigest()
        destination = history / f"{journal_digest}.json"
        if destination.exists():
            if destination.read_bytes() != encoded:
                raise ValueError("Archived recovery acknowledgement conflicts.")
        else:
            temporary = destination.with_suffix(".tmp")
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(destination)
        self.path.unlink()
        return archive_digest

    def record_health(
        self, *, worker_id: UUID, observed_at: datetime, service_version: str
    ) -> None:
        self.initialize()
        temporary = self.health_path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                {
                    "worker_id": str(worker_id),
                    "authenticated_heartbeat_at": observed_at.isoformat(),
                    "service_version": service_version,
                },
                stream,
                sort_keys=True,
                separators=(",", ":"),
            )
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.health_path)

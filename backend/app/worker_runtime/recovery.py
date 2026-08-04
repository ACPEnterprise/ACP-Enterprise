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

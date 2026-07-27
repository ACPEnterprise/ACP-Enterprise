import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.worker_control.contracts import WorkerCapability


@dataclass(frozen=True)
class WorkerRuntimeConfig:
    base_url: str
    worker_id: UUID
    private_key_file: Path
    capabilities: tuple[WorkerCapability, ...]
    heartbeat_seconds: int = 30
    request_timeout_seconds: int = 10

    @classmethod
    def from_environment(cls) -> "WorkerRuntimeConfig":
        capabilities = tuple(
            WorkerCapability(value.strip())
            for value in os.environ.get(
                "ACP_WORKER_CAPABILITIES", WorkerCapability.CONNECTIVITY.value
            ).split(",")
            if value.strip()
        )
        config = cls(
            base_url=os.environ["ACP_WORKER_BASE_URL"].rstrip("/"),
            worker_id=UUID(os.environ["ACP_WORKER_ID"]),
            private_key_file=Path(os.environ["ACP_WORKER_PRIVATE_KEY_FILE"]),
            capabilities=capabilities,
            heartbeat_seconds=int(os.environ.get("ACP_WORKER_HEARTBEAT_SECONDS", "30")),
            request_timeout_seconds=int(
                os.environ.get("ACP_WORKER_REQUEST_TIMEOUT_SECONDS", "10")
            ),
        )
        if (
            not config.base_url.startswith(("http://", "https://"))
            or not config.capabilities
            or not 10 <= config.heartbeat_seconds <= 60
            or not 1 <= config.request_timeout_seconds <= 30
        ):
            raise ValueError("Worker runtime configuration is invalid.")
        return config

    def read_private_key(self) -> str:
        stat = self.private_key_file.stat()
        if stat.st_mode & 0o077:
            raise PermissionError("Worker private key permissions must be 600.")
        value = self.private_key_file.read_text(encoding="utf-8").strip()
        if not value:
            raise ValueError("Worker private key is unavailable.")
        return value

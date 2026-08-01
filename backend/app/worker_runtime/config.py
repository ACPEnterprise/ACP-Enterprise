import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
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
    workspace_root: Path | None = None
    state_directory: Path | None = None
    service_version: str = "unknown"
    reconnect_min_seconds: int = 2
    reconnect_max_seconds: int = 30
    provider_url: str | None = None
    provider_token_file: Path | None = None

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
            workspace_root=(
                Path(os.environ["ACP_WORKER_WORKSPACE_ROOT"])
                if "ACP_WORKER_WORKSPACE_ROOT" in os.environ
                else None
            ),
            state_directory=(
                Path(os.environ["ACP_WORKER_STATE_DIRECTORY"])
                if "ACP_WORKER_STATE_DIRECTORY" in os.environ
                else None
            ),
            service_version=os.environ.get("ACP_WORKER_SERVICE_VERSION", "unknown"),
            reconnect_min_seconds=int(
                os.environ.get("ACP_WORKER_RECONNECT_MIN_SECONDS", "2")
            ),
            reconnect_max_seconds=int(
                os.environ.get("ACP_WORKER_RECONNECT_MAX_SECONDS", "30")
            ),
            provider_url=os.environ.get("ACP_WORKER_PROVIDER_URL"),
            provider_token_file=(
                Path(os.environ["ACP_WORKER_PROVIDER_TOKEN_FILE"])
                if "ACP_WORKER_PROVIDER_TOKEN_FILE" in os.environ
                else None
            ),
        )
        endpoint = urlsplit(config.base_url)
        if (
            endpoint.scheme not in {"http", "https"}
            or not endpoint.hostname
            or endpoint.username is not None
            or endpoint.password is not None
            or endpoint.query
            or endpoint.fragment
            or not config.capabilities
            or not 10 <= config.heartbeat_seconds <= 60
            or not 1 <= config.request_timeout_seconds <= 30
            or not 1
            <= config.reconnect_min_seconds
            <= config.reconnect_max_seconds
            <= 300
            or len(config.service_version) > 100
        ):
            raise ValueError("Worker runtime configuration is invalid.")
        if WorkerCapability.ENGINEERING_EXECUTE in config.capabilities and (
            config.state_directory is None
            or (
                config.workspace_root is None
                and (config.provider_url is None or config.provider_token_file is None)
            )
        ):
            raise ValueError(
                "Execution-capable worker requires isolated workspace and state roots."
            )
        if config.provider_url is not None:
            provider = urlsplit(config.provider_url)
            if provider.scheme != "http" or provider.hostname not in {
                "127.0.0.1",
                "localhost",
                "::1",
            }:
                raise ValueError("Execution Provider must use a loopback endpoint.")
        if not config.private_key_file.is_absolute():
            raise ValueError("Worker private key path must be absolute.")
        return config

    def read_private_key(self) -> str:
        stat = self.private_key_file.stat()
        if stat.st_mode & 0o077:
            raise PermissionError("Worker private key permissions must be 600.")
        value = self.private_key_file.read_text(encoding="utf-8").strip()
        if not value:
            raise ValueError("Worker private key is unavailable.")
        return value

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.platform.factory_control.schemas import FactoryLiveLaneTarget
from app.worker_control.contracts import WorkerCapability
from app.worker_control.transport.crypto import decode_private_key, encode_signature
from app.worker_runtime.client import WorkerRuntimeTransportError, WorkerTransportClient

LOGGER = logging.getLogger(__name__)
CANONICAL_LANES = {"OM1E", "OM2E", "LaptopE"}


@dataclass(frozen=True)
class LiveFactoryControlConfig:
    base_url: str
    worker_id: UUID
    private_key_file: Path
    targets: tuple[dict[str, str], ...]
    protected_sha: str
    beta_sha: str
    sync_seconds: int = 300
    request_timeout_seconds: int = 10
    health_file: Path = Path("/tmp/factory-control-health.json")

    @classmethod
    def from_environment(cls) -> LiveFactoryControlConfig:
        raw_targets: Any = json.loads(os.environ["FACTORY_CONTROL_LANE_TARGETS"])
        if not isinstance(raw_targets, list):
            raise TypeError("FACTORY_CONTROL_LANE_TARGETS must be a JSON list")
        targets: list[dict[str, str]] = []
        seen_lanes: set[str] = set()
        seen_workers: set[UUID] = set()
        for raw in raw_targets:
            if not isinstance(raw, dict):
                raise TypeError("Factory Control target must be an object")
            target = FactoryLiveLaneTarget.model_validate(raw)
            lane = target.lane_code
            enterprise = target.controlling_enterprise
            worker_id = target.worker_id
            if (
                lane not in CANONICAL_LANES
                or enterprise != lane
                or lane in seen_lanes
                or worker_id in seen_workers
            ):
                raise ValueError("Factory Control target mapping is invalid")
            seen_lanes.add(lane)
            seen_workers.add(worker_id)
            targets.append(target.model_dump(mode="json"))
        config = cls(
            base_url=os.environ["FACTORY_CONTROL_BASE_URL"].rstrip("/"),
            worker_id=UUID(os.environ["FACTORY_CONTROL_WORKER_ID"]),
            private_key_file=Path(os.environ["FACTORY_CONTROL_PRIVATE_KEY_FILE"]),
            targets=tuple(targets),
            protected_sha=os.environ["FACTORY_CONTROL_PROTECTED_SHA"],
            beta_sha=os.environ["FACTORY_CONTROL_BETA_SHA"],
            sync_seconds=int(os.environ.get("FACTORY_CONTROL_SYNC_SECONDS", "300")),
            request_timeout_seconds=int(
                os.environ.get("FACTORY_CONTROL_REQUEST_TIMEOUT_SECONDS", "10")
            ),
            health_file=Path(
                os.environ.get(
                    "FACTORY_CONTROL_HEALTH_FILE",
                    "/tmp/factory-control-health.json",
                )
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
            or not config.targets
            or not 60 <= config.sync_seconds <= 900
            or not 1 <= config.request_timeout_seconds <= 30
            or len(config.protected_sha) != 40
            or len(config.beta_sha) != 40
            or any(character not in "0123456789abcdef" for character in config.protected_sha)
            or any(character not in "0123456789abcdef" for character in config.beta_sha)
            or not config.private_key_file.is_absolute()
            or not config.health_file.is_absolute()
        ):
            raise ValueError("Factory Control live runtime configuration is invalid")
        return config

    def read_private_key(self) -> Ed25519PrivateKey:
        if self.private_key_file.stat().st_mode & 0o077:
            raise PermissionError("Factory Control private key permissions must be 600")
        return decode_private_key(self.private_key_file.read_text(encoding="utf-8").strip())


class LiveFactoryControlRuntime:
    def __init__(self, config: LiveFactoryControlConfig) -> None:
        self.config = config
        self.client = WorkerTransportClient(
            base_url=config.base_url,
            timeout_seconds=config.request_timeout_seconds,
        )
        self.private_key = config.read_private_key()

    async def publish_once(self) -> None:
        challenge = await self.client.challenge(self.config.worker_id)
        proof = encode_signature(self.private_key.sign(challenge.challenge.encode()))
        session = await self.client.establish(
            worker_id=self.config.worker_id,
            challenge=challenge,
            proof=proof,
            capabilities=(WorkerCapability.CONNECTIVITY,),
        )
        observed_at = datetime.now(timezone.utc)
        await self.client.factory_control_live_sync(
            session_id=session.session_id,
            payload={
                "observed_at": observed_at.isoformat(),
                "targets": list(self.config.targets),
            },
        )
        snapshot_key = f"live:{observed_at.strftime('%Y%m%dT%H%M%SZ')}"
        await self.client.factory_control_snapshot(
            session_id=session.session_id,
            payload={
                "snapshot_key": snapshot_key,
                "captured_at": observed_at.isoformat(),
                "protected_sha": self.config.protected_sha,
                "beta_sha": self.config.beta_sha,
            },
        )
        self.config.health_file.write_text(
            json.dumps(
                {
                    "observed_at": observed_at.isoformat(),
                    "lane_count": len(self.config.targets),
                    "protected_sha": self.config.protected_sha,
                    "beta_sha": self.config.beta_sha,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        LOGGER.info("Factory Control live synchronization completed")

    async def run(self, stop: asyncio.Event) -> None:
        delay = 2
        try:
            while not stop.is_set():
                try:
                    await self.publish_once()
                    delay = 2
                    try:
                        await asyncio.wait_for(
                            stop.wait(), timeout=self.config.sync_seconds
                        )
                    except TimeoutError:
                        continue
                except asyncio.CancelledError:
                    raise
                except (WorkerRuntimeTransportError, httpx.HTTPError, OSError) as error:
                    LOGGER.warning(
                        "Factory Control synchronization failed; retrying (%s)",
                        type(error).__name__,
                    )
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=delay)
                    except TimeoutError:
                        delay = min(delay * 2, 60)
        finally:
            await self.client.close()


async def main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(name, stop.set)
    await LiveFactoryControlRuntime(LiveFactoryControlConfig.from_environment()).run(
        stop
    )


if __name__ == "__main__":
    asyncio.run(main())

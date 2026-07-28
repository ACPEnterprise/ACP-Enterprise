from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import httpx

from app.worker_control.contracts import WorkerCapability
from app.worker_runtime.execution import AcquiredControlledOffer


class WorkerRuntimeTransportError(Exception):
    pass


@dataclass(frozen=True)
class Challenge:
    challenge_id: UUID
    challenge: str
    key_version: str


@dataclass(frozen=True)
class Session:
    session_id: UUID
    key_version: str
    next_sequence: int
    expires_at: datetime


class WorkerTransportClient:
    def __init__(self, *, base_url: str, timeout_seconds: int) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
        )

    async def challenge(self, worker_id: UUID) -> Challenge:
        response = await self._client.post(
            "/api/v1/worker-transport/sessions/challenge",
            headers={"X-Worker-ID": str(worker_id)},
        )
        self._accepted(response, 201)
        data = response.json()
        return Challenge(
            challenge_id=UUID(data["challenge_id"]),
            challenge=data["challenge"],
            key_version=data["key_version"],
        )

    async def establish(
        self,
        *,
        worker_id: UUID,
        challenge: Challenge,
        proof: str,
        capabilities: tuple[WorkerCapability, ...],
    ) -> Session:
        response = await self._client.post(
            "/api/v1/worker-transport/sessions",
            headers={"X-Worker-ID": str(worker_id)},
            json={
                "challenge_id": str(challenge.challenge_id),
                "challenge": challenge.challenge,
                "authentication_response": proof,
                "capabilities": [item.value for item in capabilities],
            },
        )
        self._accepted(response, 201)
        data = response.json()
        return Session(
            session_id=UUID(data["session_id"]),
            key_version=data["key_version"],
            next_sequence=data["next_sequence"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )

    async def heartbeat(self, *, session_id: UUID, payload: dict[str, object]) -> None:
        response = await self._client.post(
            "/api/v1/worker-transport/heartbeats",
            headers={"X-Worker-Session-ID": str(session_id)},
            json=payload,
        )
        self._accepted(response, 200)

    async def renew_lease(
        self, *, session_id: UUID, payload: dict[str, object]
    ) -> None:
        response = await self._client.post(
            "/api/v1/worker-transport/leases/refresh",
            headers={"X-Worker-Session-ID": str(session_id)},
            json=payload,
        )
        self._accepted(response, 200)

    async def poll_offers(self, *, session_id: UUID) -> tuple[dict[str, object], ...]:
        response = await self._client.get(
            f"/api/v1/worker-transport/sessions/{session_id}/offers",
            headers={"X-Worker-Session-ID": str(session_id)},
            params={"limit": 1},
        )
        self._accepted(response, 200)
        return tuple(response.json()["items"])

    async def acquire_offer(
        self, *, session_id: UUID, payload: dict[str, object]
    ) -> AcquiredControlledOffer:
        response = await self._client.post(
            "/api/v1/worker-transport/offers/acquire",
            headers={"X-Worker-Session-ID": str(session_id)},
            json=payload,
        )
        self._accepted(response, 200)
        data = response.json()
        return AcquiredControlledOffer(
            offer_id=UUID(data["offer_id"]),
            lease_id=UUID(data["lease_id"]),
            lease_version=data["lease_version"],
            workspace_id=data["workspace_id"],
            command_type=data["command_type"],
            payload=data["payload"],
        )

    async def submit_controlled_result(
        self, *, session_id: UUID, payload: dict[str, object]
    ) -> None:
        response = await self._client.post(
            "/api/v1/worker-transport/controlled-results",
            headers={"X-Worker-Session-ID": str(session_id)},
            json=payload,
        )
        self._accepted(response, 200)

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _accepted(response: httpx.Response, expected: int) -> None:
        if response.status_code != expected:
            raise WorkerRuntimeTransportError(
                f"Worker transport rejected the operation ({response.status_code})."
            )

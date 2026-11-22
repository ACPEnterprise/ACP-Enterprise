from uuid import uuid4

import httpx
import pytest
from app.worker_runtime.client import WorkerTransportClient


@pytest.mark.asyncio
async def test_factory_control_client_uses_worker_session_as_bearer() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/live-sync"):
            return httpx.Response(202, json={"events": []})
        return httpx.Response(201, json={"id": str(uuid4())})

    session_id = uuid4()
    client = WorkerTransportClient(base_url="http://test", timeout_seconds=5)
    await client.close()
    client._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handle)
    )
    try:
        await client.factory_control_live_sync(session_id=session_id, payload={})
        await client.factory_control_snapshot(session_id=session_id, payload={})
    finally:
        await client.close()

    assert len(requests) == 2
    for request in requests:
        assert request.headers["Authorization"] == f"Bearer {session_id}"
        assert "X-Worker-Session-ID" not in request.headers

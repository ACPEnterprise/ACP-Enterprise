import httpx
import pytest

from app.main import app


def test_field_service_openapi_is_bounded() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/technician/itinerary" in paths
    assert "/api/v1/technician/jobs/{job_id}" in paths
    assert "/api/v1/technician/jobs/{job_id}/notes" in paths
    assert "/api/v1/technician/jobs/{job_id}/customer-approval" in paths
    assert "/api/v1/technician/jobs/{job_id}/invoice-handoff" in paths


@pytest.mark.asyncio
async def test_field_service_fails_closed_without_authentication() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        itinerary = await client.get(
            "/api/v1/technician/itinerary", params={"service_date": "2026-08-27"}
        )
        note = await client.post(
            "/api/v1/technician/jobs/00000000-0000-0000-0000-000000000001/notes",
            json={
                "content": "Work performed safely.",
                "idempotency_key": "field-note-test",
            },
        )
    assert itinerary.status_code == 401
    assert note.status_code == 401

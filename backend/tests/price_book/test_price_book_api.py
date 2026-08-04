import httpx
import pytest
from app.main import app
from app.platform.permissions.catalog import permission_catalog
from app.platform.permissions.codes import PriceBookPermission


def test_price_book_permissions_and_openapi_are_bounded() -> None:
    codes = {definition.code for definition in permission_catalog.definitions}
    assert PriceBookPermission.ALL <= codes
    paths = app.openapi()["paths"]
    assert "/api/v1/price-book" in paths
    assert "/api/v1/price-book/service-items/{item_id}/versions" in paths
    assert "/api/v1/price-book/versions/{version_id}/activate" in paths
    assert "/api/v1/price-book/service-items/{item_id}/snapshots" in paths
    assert "/api/v1/price-book/option-groups" in paths
    assert "/api/v1/price-book/option-groups/{group_id}/options" in paths
    assert "/api/v1/price-book/versions/{version_id}/draft" in paths
    assert "/api/v1/price-book/versions/{version_id}/inactivate" in paths
    assert "/api/v1/price-book/versions/{version_id}/archive" in paths
    assert "/api/v1/price-book/snapshots/{snapshot_id}" in paths
    assert "/api/v1/price-book/audit" in paths


@pytest.mark.asyncio
async def test_price_book_api_fails_closed_without_authentication() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        read = await client.get("/api/v1/price-book")
        manage = await client.post(
            "/api/v1/price-book/categories", json={"code": "DRAIN", "name": "Drain"}
        )
        activate = await client.post(
            "/api/v1/price-book/versions/00000000-0000-0000-0000-000000000001/activate",
            json={"expected_version": 1, "reason": "test"},
        )
    assert read.status_code == 401
    assert manage.status_code == 401
    assert activate.status_code == 401

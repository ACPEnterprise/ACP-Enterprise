from dataclasses import replace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.platform.contracts.manifest import (
    PlatformContractDriftError,
    platform_contract_manifest,
)
from app.platform.contracts.router import engineering_router, router
from app.platform.permissions.codes import PriceBookPermission


def test_platform_contract_is_deterministic_and_contains_price_book() -> None:
    assert len(platform_contract_manifest.fingerprint) == 64
    assert set(PriceBookPermission.ALL)
    platform_contract_manifest.assert_expected(platform_contract_manifest.fingerprint)
    with pytest.raises(PlatformContractDriftError):
        platform_contract_manifest.assert_expected("0" * 64)
    assert replace(platform_contract_manifest) == platform_contract_manifest


@pytest.mark.asyncio
async def test_enterprise_and_mission_contract_endpoints_are_identical() -> None:
    app = FastAPI()
    app.include_router(router)
    app.include_router(engineering_router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        enterprise = await client.get("/api/v1/platform/contracts")
        mission = await client.get("/api/v1/engineering/platform-contracts")
    assert enterprise.status_code == mission.status_code == 200
    assert enterprise.json() == mission.json()

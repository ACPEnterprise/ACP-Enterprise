from fastapi import APIRouter

from app.platform.contracts.manifest import platform_contract_manifest

router = APIRouter(prefix="/api/v1/platform", tags=["Platform Contracts"])
engineering_router = APIRouter(
    prefix="/api/v1/engineering", tags=["Platform Contracts"]
)


@router.get("/contracts")
async def platform_contracts() -> dict[str, str]:
    """Expose bounded compatibility metadata for deployment drift checks."""
    return platform_contract_manifest.safe_dict()


engineering_router.add_api_route(
    "/platform-contracts",
    platform_contracts,
    methods=["GET"],
    include_in_schema=False,
)

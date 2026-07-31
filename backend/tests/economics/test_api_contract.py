from fastapi import FastAPI

from app.economics.router import router


def test_economics_api_is_read_only() -> None:
    app = FastAPI()
    app.include_router(router)
    economics_operations = {
        method
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/v1/economics")
        for method in operations
    }

    assert economics_operations == {"get"}

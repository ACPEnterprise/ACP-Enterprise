from app.data_quality.router import router
from fastapi.routing import APIRoute


def test_data_quality_surface_is_read_only() -> None:
    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    assert {route.path for route in routes} == {
        "/api/v1/data-quality/catalog", "/api/v1/data-quality/summary"
    }
    assert all(route.methods == {"GET"} for route in routes)

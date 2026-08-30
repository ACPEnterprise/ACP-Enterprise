from app.main import app

HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
INTENTIONAL_NON_BEARER_BOUNDARIES = {
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/health/live"),
    ("GET", "/health/ready"),
    ("GET", "/api/v1/integrations/qbo/oauth/callback"),
    ("GET", "/api/v1/integrations/qbo/production/oauth/callback"),
    ("GET", "/api/v1/platform/contracts"),
    ("POST", "/api/v1/auth/email-verification/confirm"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/password-reset/confirm"),
    ("POST", "/api/v1/auth/password-reset/request"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/identity-onboarding/activate/complete"),
    ("GET", "/api/v1/worker-transport/sessions/{session_id}/offers"),
    (
        "GET",
        "/api/v1/worker-transport/sessions/{session_id}/repository-readiness-targets",
    ),
    (
        "GET",
        "/api/v1/worker-transport/sessions/{session_id}/recovery-acknowledgements",
    ),
    (
        "GET",
        "/api/v1/worker-transport/sessions/{session_id}/workstream-controls",
    ),
    ("POST", "/api/v1/worker-transport/cancellations/acknowledge"),
    ("POST", "/api/v1/worker-transport/composition-results"),
    ("POST", "/api/v1/worker-transport/compositions/acknowledge"),
    ("POST", "/api/v1/worker-transport/compositions/next"),
    ("POST", "/api/v1/worker-transport/controlled-results"),
    ("POST", "/api/v1/worker-transport/heartbeats"),
    ("POST", "/api/v1/worker-transport/leases/refresh"),
    ("POST", "/api/v1/worker-transport/offers/acquire"),
    ("POST", "/api/v1/worker-transport/progress"),
    ("POST", "/api/v1/worker-transport/repository-readiness"),
    (
        "POST",
        "/api/v1/worker-transport/recovery-acknowledgements/{acknowledgement_id}/applied",
    ),
    ("POST", "/api/v1/worker-transport/results"),
    ("POST", "/api/v1/worker-transport/sessions"),
    ("POST", "/api/v1/worker-transport/sessions/challenge"),
    ("POST", "/api/v1/worker-transport/workstream-controls/acknowledge"),
    ("POST", "/api/v1/worker-transport/workstream-runtime"),
}


def test_every_non_bearer_http_boundary_is_explicitly_reviewed() -> None:
    schema = app.openapi()
    observed = {
        (method.upper(), path)
        for path, path_item in schema["paths"].items()
        for method, operation in path_item.items()
        if method.upper() in HTTP_METHODS and not operation.get("security")
    }

    assert observed == INTENTIONAL_NON_BEARER_BOUNDARIES
    assert ("GET", "/api/v1/events") not in observed
    assert ("GET", "/api/v1/events/latest") not in observed
    assert ("POST", "/api/v1/events") not in observed

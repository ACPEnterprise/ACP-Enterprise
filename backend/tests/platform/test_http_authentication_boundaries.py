from app.main import app

HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
PUBLIC_OPERATIONAL_BOUNDARIES = {
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/health/live"),
    ("GET", "/health/ready"),
    ("GET", "/api/v1/platform/contracts"),
}
OAUTH_CALLBACK_BOUNDARIES = {
    ("GET", "/api/v1/integrations/qbo/oauth/callback"),
    ("GET", "/api/v1/integrations/qbo/production/oauth/callback"),
}
IDENTITY_BOOTSTRAP_AND_RECOVERY_BOUNDARIES = {
    ("POST", "/api/v1/auth/email-verification/confirm"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/password-reset/confirm"),
    ("POST", "/api/v1/auth/password-reset/request"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/identity-onboarding/activate/complete"),
}
WORKER_PROOF_BOUNDARIES = {
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
NON_BEARER_BOUNDARY_JUSTIFICATIONS = {
    **{
        boundary: "Public health, service metadata, or contract discovery."
        for boundary in PUBLIC_OPERATIONAL_BOUNDARIES
    },
    **{
        boundary: "OAuth callback authenticated by protected state and provider response."
        for boundary in OAUTH_CALLBACK_BOUNDARIES
    },
    **{
        boundary: (
            "Identity bootstrap or recovery authenticated by credentials, a rotating "
            "refresh token, or a one-time protected token."
        )
        for boundary in IDENTITY_BOOTSTRAP_AND_RECOVERY_BOUNDARIES
    },
    **{
        boundary: (
            "Worker transport uses challenge-established, expiring worker sessions "
            "and signed message proofs instead of a human access-token bearer."
        )
        for boundary in WORKER_PROOF_BOUNDARIES
    },
}


def test_every_non_bearer_http_boundary_is_explicitly_reviewed() -> None:
    schema = app.openapi()
    security_schemes = schema["components"]["securitySchemes"]
    protected_operations = [
        operation
        for path_item in schema["paths"].values()
        for method, operation in path_item.items()
        if method.upper() in HTTP_METHODS and operation.get("security")
    ]
    observed = {
        (method.upper(), path)
        for path, path_item in schema["paths"].items()
        for method, operation in path_item.items()
        if method.upper() in HTTP_METHODS and not operation.get("security")
    }

    assert observed == set(NON_BEARER_BOUNDARY_JUSTIFICATIONS)
    assert all(NON_BEARER_BOUNDARY_JUSTIFICATIONS.values())
    assert all(
        security_schemes[scheme_name]["type"] == "http"
        and security_schemes[scheme_name]["scheme"] == "bearer"
        for operation in protected_operations
        for requirement in operation["security"]
        for scheme_name in requirement
    )
    assert ("GET", "/api/v1/events") not in observed
    assert ("GET", "/api/v1/events/latest") not in observed
    assert ("POST", "/api/v1/events") not in observed
    assert not any("/factory-control/" in path for _, path in observed)

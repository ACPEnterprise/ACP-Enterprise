from app.engineering_control.repository_authorization.errors import (
    RepositoryAuthorizationConflictError,
    RepositoryAuthorizationIneligibleError,
    RepositoryAuthorizationNotFoundError,
)
from app.engineering_control.repository_authorization.router import (
    _http_error as authorization_error,
)
from app.engineering_control.repository_operation.errors import (
    RepositoryOperationConflictError,
    RepositoryOperationNotFoundError,
    RepositoryOperationReconciliationRequiredError,
    RepositoryOperationValidationError,
)
from app.engineering_control.repository_operation.router import (
    _error as operation_error,
)
from app.engineering_control.review.errors import (
    EngineeringReviewConflictError,
    EngineeringReviewIneligibleError,
    EngineeringReviewNotFoundError,
)
from app.engineering_control.review.router import _http_error as review_error


def test_privileged_engineering_failures_are_classified_and_non_reflective() -> None:
    canary = "token=privileged-engineering-canary internal/repository/path"
    failures = (
        authorization_error(RepositoryAuthorizationNotFoundError(canary)),
        authorization_error(RepositoryAuthorizationConflictError(canary)),
        authorization_error(RepositoryAuthorizationIneligibleError(canary)),
        operation_error(RepositoryOperationNotFoundError(canary)),
        operation_error(RepositoryOperationConflictError(canary)),
        operation_error(RepositoryOperationReconciliationRequiredError(canary)),
        operation_error(RepositoryOperationValidationError(canary)),
        review_error(EngineeringReviewNotFoundError(canary)),
        review_error(EngineeringReviewConflictError(canary)),
        review_error(EngineeringReviewIneligibleError(canary)),
    )

    assert [failure.detail["recovery"] for failure in failures] == [
        "TERMINAL_FAILURE",
        "RETRY_AFTER_REFRESH",
        "USER_CORRECTION_REQUIRED",
        "TERMINAL_FAILURE",
        "RETRY_AFTER_REFRESH",
        "RECONCILIATION_REQUIRED",
        "USER_CORRECTION_REQUIRED",
        "TERMINAL_FAILURE",
        "RETRY_AFTER_REFRESH",
        "USER_CORRECTION_REQUIRED",
    ]
    assert all(canary not in str(failure.detail) for failure in failures)

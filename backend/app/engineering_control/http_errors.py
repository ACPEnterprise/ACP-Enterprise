from fastapi import HTTPException, status

from app.engineering_control.errors import (
    EngineeringCommandApprovalMismatchError,
    EngineeringCommandExecutionUnavailableError,
    EngineeringCommandExpirationError,
    EngineeringCommandExpiredError,
    EngineeringCommandIdempotencyConflictError,
    EngineeringCommandLifecycleError,
    EngineeringCommandNotFoundError,
    EngineeringCommandPermissionError,
    EngineeringCommandRepositoryPolicyError,
    EngineeringCommandStaleVersionError,
    EngineeringCommandUnsafeInstructionError,
    EngineeringCommandValidationError,
    EngineeringControlError,
)


def engineering_http_error(error: EngineeringControlError) -> HTTPException:
    if isinstance(error, EngineeringCommandNotFoundError):
        code, message, http_status = (
            "engineering_command_not_found",
            "Engineering Command was not found.",
            status.HTTP_404_NOT_FOUND,
        )
    elif isinstance(error, EngineeringCommandPermissionError):
        code, message, http_status = (
            "engineering_command_permission_denied",
            "Permission denied.",
            status.HTTP_403_FORBIDDEN,
        )
    elif isinstance(error, EngineeringCommandIdempotencyConflictError):
        code, message, http_status = (
            "engineering_command_idempotency_conflict",
            "The idempotency key was already used for another request.",
            status.HTTP_409_CONFLICT,
        )
    elif isinstance(error, EngineeringCommandStaleVersionError):
        code, message, http_status = (
            "engineering_command_stale",
            "The command changed and must be reviewed again.",
            status.HTTP_409_CONFLICT,
        )
    elif isinstance(error, EngineeringCommandApprovalMismatchError):
        code, message, http_status = (
            "engineering_command_approval_mismatch",
            "The reviewed command evidence no longer matches.",
            status.HTTP_409_CONFLICT,
        )
    elif isinstance(error, EngineeringCommandExpiredError):
        code, message, http_status = (
            "engineering_command_expired",
            "The Engineering Command has expired.",
            status.HTTP_409_CONFLICT,
        )
    elif isinstance(error, EngineeringCommandLifecycleError):
        code, message, http_status = (
            "engineering_command_lifecycle_conflict",
            "The command is not eligible for this action.",
            status.HTTP_409_CONFLICT,
        )
    elif isinstance(error, EngineeringCommandExecutionUnavailableError):
        code, message, http_status = (
            "engineering_execution_not_connected",
            "Engineering execution is not connected.",
            status.HTTP_409_CONFLICT,
        )
    elif isinstance(
        error,
        (
            EngineeringCommandValidationError,
            EngineeringCommandUnsafeInstructionError,
            EngineeringCommandRepositoryPolicyError,
            EngineeringCommandExpirationError,
        ),
    ):
        code, message, http_status = (
            "engineering_command_invalid",
            "The Engineering Command request is invalid.",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    else:
        code, message, http_status = (
            "engineering_command_error",
            "The Engineering Command operation could not be completed.",
            status.HTTP_400_BAD_REQUEST,
        )
    return HTTPException(
        status_code=http_status, detail={"code": code, "message": message}
    )

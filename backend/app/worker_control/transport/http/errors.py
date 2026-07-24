from fastapi import HTTPException, status

from app.worker_control.transport.errors import (
    TransportAuthenticationError,
    TransportBindingError,
    TransportCapabilityError,
    TransportChallengeError,
    TransportMessageError,
    TransportReplayError,
    TransportSequenceError,
    TransportSessionError,
    TransportTimestampError,
    WorkerTransportError,
)


def transport_http_error(error: WorkerTransportError) -> HTTPException:
    if isinstance(error, (TransportAuthenticationError, TransportBindingError)):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "worker_transport_not_found"},
        )
    if isinstance(error, (TransportReplayError, TransportSequenceError)):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "worker_transport_replay_or_sequence"},
        )
    if isinstance(error, (TransportSessionError, TransportChallengeError)):
        return HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"code": "worker_transport_expired"},
        )
    if isinstance(
        error,
        (TransportTimestampError, TransportCapabilityError, TransportMessageError),
    ):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "worker_transport_invalid"},
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "worker_transport_error"},
    )

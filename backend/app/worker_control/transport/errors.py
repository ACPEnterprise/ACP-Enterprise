class WorkerTransportError(Exception):
    """Base class for fail-closed worker transport errors."""


class TransportAuthenticationError(WorkerTransportError):
    pass


class TransportChallengeError(WorkerTransportError):
    pass


class TransportSessionError(WorkerTransportError):
    pass


class TransportReplayError(WorkerTransportError):
    pass


class TransportSequenceError(WorkerTransportError):
    pass


class TransportTimestampError(WorkerTransportError):
    pass


class TransportBindingError(WorkerTransportError):
    pass


class TransportCapabilityError(WorkerTransportError):
    pass


class TransportMessageError(WorkerTransportError):
    pass

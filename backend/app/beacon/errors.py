class BeaconLifecycleError(Exception):
    """Base error for rejected Beacon lifecycle commands."""


class BeaconSignalNotFoundError(BeaconLifecycleError):
    pass


class BeaconSignalStaleError(BeaconLifecycleError):
    pass


class BeaconSnoozeInvalidError(BeaconLifecycleError):
    pass


class BeaconWorkflowConflictError(BeaconLifecycleError):
    pass


class BeaconWorkflowOwnerInvalidError(BeaconLifecycleError):
    pass

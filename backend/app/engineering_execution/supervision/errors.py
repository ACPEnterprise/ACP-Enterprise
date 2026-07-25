class SupervisionError(Exception):
    code = "supervision_error"


class SupervisionNotFoundError(SupervisionError):
    code = "supervision_not_found"


class SupervisionConflictError(SupervisionError):
    code = "supervision_conflict"


class SupervisionCapabilityError(SupervisionError):
    code = "supervision_capability_mismatch"


class SupervisionTransitionError(SupervisionError):
    code = "supervision_transition_invalid"


class SupervisionIneligibleError(SupervisionError):
    code = "supervision_ineligible"

class ExecutionCompositionError(Exception):
    code = "execution_composition_error"


class CompositionNotFoundError(ExecutionCompositionError):
    code = "composition_not_found"


class CompositionPermissionError(ExecutionCompositionError):
    code = "composition_permission_denied"


class CompositionIneligibleError(ExecutionCompositionError):
    code = "composition_ineligible"


class CompositionEvidenceMismatchError(ExecutionCompositionError):
    code = "composition_evidence_mismatch"


class CompositionCapabilityError(ExecutionCompositionError):
    code = "composition_capability_mismatch"


class CompositionConflictError(ExecutionCompositionError):
    code = "composition_conflict"


class AttemptTransitionError(ExecutionCompositionError):
    code = "attempt_transition_invalid"


class StaleAttemptVersionError(ExecutionCompositionError):
    code = "attempt_version_stale"


class ProgressValidationError(ExecutionCompositionError):
    code = "progress_invalid"


class ResultValidationError(ExecutionCompositionError):
    code = "result_invalid"

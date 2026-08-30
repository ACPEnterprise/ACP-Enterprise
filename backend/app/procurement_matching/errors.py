class ProcurementMatchingError(ValueError):
    pass


class ProcurementMatchingNotFound(ProcurementMatchingError):
    pass


class ProcurementMatchingConflict(ProcurementMatchingError):
    pass


class ProcurementMatchingValidation(ProcurementMatchingError):
    pass

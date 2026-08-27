class FieldServiceError(Exception):
    pass


class FieldServiceNotFound(FieldServiceError):
    pass


class FieldServiceConflict(FieldServiceError):
    pass


class FieldServiceValidation(FieldServiceError):
    pass

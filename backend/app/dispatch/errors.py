class DispatchError(Exception):
    pass


class DispatchNotFound(DispatchError):
    pass


class DispatchConflict(DispatchError):
    pass


class DispatchValidation(DispatchError):
    pass

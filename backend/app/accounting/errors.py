class AccountingError(Exception):
    """Base error for rejected Accounting operations."""


class AccountingNotFound(AccountingError):
    pass


class AccountingConflict(AccountingError):
    pass


class AccountingValidation(AccountingError):
    pass


class AccountingPermissionDenied(AccountingError):
    pass

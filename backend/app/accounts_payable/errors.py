class AccountsPayableError(Exception):
    """Base fail-closed AP error."""


class APNotFound(AccountsPayableError):
    pass


class APConflict(AccountsPayableError):
    pass


class APValidation(AccountsPayableError):
    pass

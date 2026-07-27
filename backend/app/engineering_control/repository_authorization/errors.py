class RepositoryAuthorizationError(Exception):
    """Base error for repository-authorization policy decisions."""


class RepositoryAuthorizationNotFoundError(RepositoryAuthorizationError):
    pass


class RepositoryAuthorizationIneligibleError(RepositoryAuthorizationError):
    pass


class RepositoryAuthorizationConflictError(RepositoryAuthorizationError):
    pass


class RepositoryAuthorizationEvidenceMismatchError(RepositoryAuthorizationError):
    pass

class RepositoryOperationError(Exception):
    """Base bounded repository-operation failure."""


class RepositoryOperationNotFoundError(RepositoryOperationError):
    pass


class RepositoryOperationPermissionError(RepositoryOperationError):
    pass


class RepositoryOperationValidationError(RepositoryOperationError):
    pass


class RepositoryOperationConflictError(RepositoryOperationError):
    pass


class RepositoryOperationStateError(RepositoryOperationError):
    pass


class RepositoryOperationGitError(RepositoryOperationError):
    def __init__(self, classification: str, detail: str) -> None:
        super().__init__(detail)
        self.classification = classification
        self.detail = detail


class RepositoryOperationReconciliationRequiredError(RepositoryOperationError):
    pass

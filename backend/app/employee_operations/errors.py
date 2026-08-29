class EmployeeOperationsError(Exception):
    """Base error for employee self-service projections."""


class EmployeeIdentityNotReady(EmployeeOperationsError):
    """The authenticated Membership has no active native Employee."""

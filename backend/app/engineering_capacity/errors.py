class EngineeringCapacityError(Exception):
    code = "engineering_capacity_error"
    status_code = 400


class CapacityNotFoundError(EngineeringCapacityError):
    code = "engineering_capacity_not_found"
    status_code = 404


class CapacityConflictError(EngineeringCapacityError):
    code = "engineering_capacity_conflict"
    status_code = 409


class CapacityUnavailableError(EngineeringCapacityError):
    code = "engineering_capacity_unavailable"
    status_code = 409


class CapacityReconciliationRequiredError(EngineeringCapacityError):
    code = "engineering_capacity_reconciliation_required"
    status_code = 409

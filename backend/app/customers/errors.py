from uuid import UUID


class CustomerError(Exception):
    """Base class for expected Customer Management errors."""


class CustomerNotFoundError(CustomerError):
    def __init__(self, customer_id: UUID) -> None:
        super().__init__(f"Customer {customer_id} was not found.")


class CustomerArchivedError(CustomerError):
    def __init__(self, customer_id: UUID) -> None:
        super().__init__(f"Customer {customer_id} is archived and cannot be changed.")


class CustomerStatusTransitionError(CustomerError):
    def __init__(self, current_status: str, requested_status: str) -> None:
        self.current_status = current_status
        self.requested_status = requested_status
        super().__init__(
            f"Customer status cannot change from {current_status} to {requested_status}."
        )


class CustomerChildNotFoundError(CustomerError):
    def __init__(self, resource: str, resource_id: UUID) -> None:
        super().__init__(f"{resource} {resource_id} was not found for this customer.")

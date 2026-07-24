from enum import StrEnum

from app.engineering_control.records import EngineeringApprovalState


class EngineeringCommandEventType(StrEnum):
    CREATED = "command_created"
    APPROVED = "command_approved"
    CANCELED = "command_canceled"
    EXPIRED = "command_expired"


CANCELLABLE_STATES = frozenset(
    {
        EngineeringApprovalState.AWAITING_APPROVAL,
        EngineeringApprovalState.APPROVED,
    }
)

EXPIRABLE_STATES = CANCELLABLE_STATES

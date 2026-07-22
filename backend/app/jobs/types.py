from enum import StrEnum


class JobStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class JobPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"
    EMERGENCY = "emergency"

    @property
    def rank(self) -> int:
        return {
            JobPriority.LOW: 10,
            JobPriority.NORMAL: 20,
            JobPriority.HIGH: 30,
            JobPriority.URGENT: 40,
            JobPriority.EMERGENCY: 50,
        }[self]


class JobPauseReason(StrEnum):
    CUSTOMER_UNAVAILABLE = "customer_unavailable"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_MATERIAL = "awaiting_material"
    SAFETY_CONDITION = "safety_condition"
    WEATHER = "weather"
    OPERATIONAL_HOLD = "operational_hold"


class JobCancellationReason(StrEnum):
    CUSTOMER_CANCELLED = "customer_cancelled"
    DUPLICATE = "duplicate"
    CREATED_IN_ERROR = "created_in_error"
    SCOPE_DECLINED = "scope_declined"
    UNABLE_TO_PERFORM = "unable_to_perform"


class JobReopeningReason(StrEnum):
    ADDITIONAL_WORK_REQUIRED = "additional_work_required"
    INCOMPLETE_WORK = "incomplete_work"
    CORRECTION_REQUIRED = "correction_required"
    CUSTOMER_CALLBACK = "customer_callback"
    ADMINISTRATIVE_CORRECTION = "administrative_correction"

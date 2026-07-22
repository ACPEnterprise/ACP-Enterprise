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

from enum import StrEnum


class EstimateStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class EstimateAcceptanceStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class EstimateRevisionStatus(StrEnum):
    DRAFT = "draft"


class EstimateDecisionType(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"

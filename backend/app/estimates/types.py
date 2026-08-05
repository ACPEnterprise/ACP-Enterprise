from enum import StrEnum


class EstimateStatus(StrEnum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class EstimateAcceptanceStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"


class EstimateRevisionStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"

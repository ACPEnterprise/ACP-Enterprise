from enum import Enum


class EngineeringReviewState(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class EngineeringReviewDecision(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"

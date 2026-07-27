class EngineeringReviewError(Exception):
    """Base error for bounded owner-review operations."""


class EngineeringReviewNotFoundError(EngineeringReviewError):
    pass


class EngineeringReviewIneligibleError(EngineeringReviewError):
    pass


class EngineeringReviewConflictError(EngineeringReviewError):
    pass


class EngineeringReviewDigestMismatchError(EngineeringReviewError):
    pass

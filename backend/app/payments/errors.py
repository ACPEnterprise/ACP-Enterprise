class PaymentError(Exception):
    """Base payment boundary error safe for API presentation."""


class PaymentNotFound(PaymentError):
    pass


class PaymentConflict(PaymentError):
    pass


class PaymentValidation(PaymentError):
    pass


class PaymentSecurityError(PaymentError):
    pass

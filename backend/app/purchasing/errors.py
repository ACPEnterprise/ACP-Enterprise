class PurchasingError(Exception):
    """Base Purchasing failure."""


class PurchasingNotFound(PurchasingError):
    pass


class PurchasingConflict(PurchasingError):
    pass


class PurchasingValidation(PurchasingError):
    pass

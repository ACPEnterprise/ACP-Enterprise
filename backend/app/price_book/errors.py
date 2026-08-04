class PriceBookError(ValueError):
    pass


class PriceBookNotFound(PriceBookError):
    pass


class PriceBookConflict(PriceBookError):
    pass


class PriceBookValidation(PriceBookError):
    pass

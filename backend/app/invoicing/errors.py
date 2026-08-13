class InvoiceError(Exception):
    pass


class InvoiceNotFound(InvoiceError):
    pass


class InvoiceConflict(InvoiceError):
    pass


class InvoiceValidation(InvoiceError):
    pass

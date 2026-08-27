class FinancialReportingError(Exception):
    pass


class ReportingRequestError(FinancialReportingError):
    pass


class ReportingNotFound(FinancialReportingError):
    pass


class ReportingIntegrityError(FinancialReportingError):
    """Authoritative ledger evidence cannot support a valid report."""

class ExecutionProviderError(Exception):
    """Base error for provider-neutral execution failures."""

    code = "provider_error"


class DuplicateProviderError(ExecutionProviderError):
    code = "duplicate_provider"


class ProviderNotFoundError(ExecutionProviderError):
    code = "provider_not_found"


class ProviderUnavailableError(ExecutionProviderError):
    code = "provider_unavailable"


class ProviderCapabilityError(ExecutionProviderError):
    code = "provider_capability_mismatch"


class ProviderAuthenticationError(ExecutionProviderError):
    code = "provider_authentication_failed"


class ProviderRequestError(ExecutionProviderError):
    code = "provider_request_rejected"

class AuthenticationError(Exception):
    """Base class for expected authentication failures."""


class InvalidCredentialsError(AuthenticationError):
    pass


class InvalidTokenError(AuthenticationError):
    pass


class RefreshTokenReuseError(InvalidTokenError):
    pass


class SessionInvalidError(AuthenticationError):
    pass


class PasswordPolicyError(AuthenticationError):
    pass


class RateLimitExceededError(AuthenticationError):
    pass


class RateLimitUnavailableError(AuthenticationError):
    pass

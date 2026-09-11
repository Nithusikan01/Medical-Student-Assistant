class AuthError(Exception):
    """Base class for authentication and registration failures."""


class InvalidCredentialsError(AuthError):
    pass


class InvalidTokenError(AuthError):
    pass


class EmailAlreadyRegisteredError(AuthError):
    pass


class RegistrationNotAllowedError(AuthError):
    pass


class InactiveUserError(AuthError):
    pass

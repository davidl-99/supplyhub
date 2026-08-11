class AuthenticationError(Exception):
    pass


class InvalidCredentialsError(AuthenticationError):
    pass


class InactiveAuthenticatedUserError(AuthenticationError):
    pass

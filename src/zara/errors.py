class InternalServerError(Exception):
    """Base class for all server-related errors."""

    pass


class AuthenticationError(Exception):
    pass


class UnauthenticatedError(AuthenticationError):
    pass


class MissingTranslationKeyError(InternalServerError):
    """Raised when a translation key is missing."""

    def __init__(self, key):
        self.key = key
        super().__init__(f"Missing translation key: {key}")


class ValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(errors)


class DatabaseError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


class DuplicateResourceError(DatabaseError):
    def __init__(self, message):
        self.message = message
        super().__init__(message)


class ResourceNotFoundError(DatabaseError):
    def __init__(self, message):
        self.message = message
        super().__init__(message)

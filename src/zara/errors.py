class BaseError(Exception):
    status_code = 500  # Default to Internal Server Error

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class InternalServerError(BaseError):
    status_code = 500


class AuthenticationError(BaseError):
    status_code = 401


class UnauthenticatedError(AuthenticationError):
    pass


class ForbiddenError(BaseError):
    status_code = 403


class NotFoundError(BaseError):
    status_code = 404


class ValidationError(BaseError):
    status_code = 422

    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


class MissingTranslationKeyError(InternalServerError):
    def __init__(self, key):
        self.key = key
        super().__init__(f"Missing translation key: {key}")


class DatabaseError(BaseError):
    status_code = 500


class DuplicateResourceError(DatabaseError):
    status_code = 409


class ResourceNotFoundError(NotFoundError):
    pass


class BadRequestError(BaseError):
    status_code = 400


class MethodNotAllowedError(BaseError):
    status_code = 405


class ConflictError(BaseError):
    status_code = 409


class TooManyRequestsError(BaseError):
    status_code = 429


class ServiceUnavailableError(BaseError):
    status_code = 503


class DatabaseInputValidationError(BaseError):
    status_code = 422

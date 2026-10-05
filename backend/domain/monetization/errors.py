"""Business failures for internal monetization."""

from domain.errors import DomainError


class MonetizationError(DomainError):
    """A monetization operation cannot satisfy a business rule."""


class MonetizationValidationError(MonetizationError):
    """The supplied conditions or context are invalid."""


class MonetizationConflictError(MonetizationError):
    """A valid operation conflicts with the current financial state."""


class MonetizationAccessDeniedError(MonetizationError):
    """The actor is not entitled to the requested financial action."""


MonetizationValidation = MonetizationValidationError
MonetizationConflict = MonetizationConflictError
MonetizationAccessDenied = MonetizationAccessDeniedError

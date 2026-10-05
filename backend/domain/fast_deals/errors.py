"""Fast deal errors. No HTTP concepts: the application layer maps them to statuses."""
from __future__ import annotations

from domain.errors import DomainError


class FastDealError(DomainError):
    """Base of every fast deal rule violation."""


class FastDealNotFoundError(FastDealError):
    """The deal, position, file or invitation does not exist or is not visible.

    A foreign resource is indistinguishable from a missing one: the message never
    carries data about the client or a VIN.
    """

    def __init__(self, msg: str = "Сделка не найдена") -> None:
        super().__init__(msg)


class FastDealAccessDeniedError(FastDealError):
    def __init__(self, msg: str = "Недостаточно прав для этого действия") -> None:
        super().__init__(msg)


class FastDealValidationError(FastDealError):
    """A form or business field is invalid (422); ``field`` points at the input."""

    def __init__(self, msg: str, *, field: str | None = None) -> None:
        super().__init__(msg)
        self.field = field


class FastDealStateError(FastDealError):
    """The action is not allowed in the current state (409)."""


class FastDealConflictError(FastDealError):
    """Uniqueness or concurrent-change conflict that is not a reserve conflict (409)."""


class FastDealReserveConflictError(FastDealError):
    """A unit cannot be reserved. The whole send is rolled back (409)."""

    def __init__(
        self, msg: str, *, vin: str | None = None, source_number: str | None = None
    ) -> None:
        super().__init__(msg)
        self.vin = vin
        self.source_number = source_number


class FastDealVersionConflictError(FastDealError):
    """The ``If-Match`` version is stale (412)."""

    def __init__(self, msg: str = "Сделка изменилась. Обновите карточку") -> None:
        super().__init__(msg)


class FastDealVersionRequiredError(FastDealError):
    """The mutation has no ``If-Match`` header (428)."""

    def __init__(self, msg: str = "Передайте заголовок If-Match с версией сделки") -> None:
        super().__init__(msg)


class FastDealFileTooLargeError(FastDealError):
    """A file is larger than the allowed size (413)."""

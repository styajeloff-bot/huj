"""Domain entities for proxy operations."""
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ProxyRequest:
    """Domain entity representing a proxy request."""

    path: str
    method: str
    headers: dict[str, str] = field(default_factory=dict)
    content: bytes | None = None
    params: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        """Validate proxy request business rules."""
        if not self.path:
            msg = "Path cannot be empty"
            raise ValueError(msg)
        if not self.method:
            msg = "Method cannot be empty"
            raise ValueError(msg)
        allowed_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
        if self.method not in allowed_methods:
            msg = f"Method must be one of {allowed_methods}"
            raise ValueError(msg)


@dataclass
class ProxyResponse:
    """Domain entity representing a proxy response."""

    status_code: int
    headers: dict[str, str]
    content: bytes
    duration_ms: float

    @property
    def is_success(self) -> bool:
        """Check if response is successful (2xx)."""
        return 200 <= self.status_code < 300

    @property
    def is_error(self) -> bool:
        """Check if response is error (4xx, 5xx)."""
        return self.status_code >= 400

    def validate(self) -> None:
        """Validate response business rules."""
        if self.status_code < 0:
            msg = "Status code cannot be negative"
            raise ValueError(msg)

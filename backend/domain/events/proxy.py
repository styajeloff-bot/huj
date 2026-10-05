"""Domain events for proxy operations."""
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class DomainEvent:
    """Base domain event."""

    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class RequestProxied(DomainEvent):
    """Event fired when request is successfully proxied."""

    path: str = ""
    method: str = ""
    status_code: int = 0
    duration_ms: float = 0.0

    def to_log_string(self) -> str:
        """Format for logging."""
        return f"RequestProxied: {self.method} {self.path} -> {self.status_code} ({self.duration_ms:.1f}ms)"


@dataclass
class RequestFailed(DomainEvent):
    """Event fired when proxy request fails."""

    path: str = ""
    method: str = ""
    error: str = ""
    duration_ms: float = 0.0

    def to_log_string(self) -> str:
        """Format for logging."""
        return f"RequestFailed: {self.method} {self.path} -> ERROR: {self.error} ({self.duration_ms:.1f}ms)"


@dataclass
class ServiceUnavailable(DomainEvent):
    """Event fired when Express backend is unavailable."""

    path: str = ""
    method: str = ""

    def to_log_string(self) -> str:
        """Format for logging."""
        return f"ServiceUnavailable: {self.method} {self.path} -> Express backend unreachable"

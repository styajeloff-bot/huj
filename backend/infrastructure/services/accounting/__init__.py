"""Concrete accounting-provider implementations and factory.

Swapping Parser API for another source (SPARK, Kontur, ФНС GIRBO, …)
requires only a new implementation next to `parser_api_provider.py`
plus a `settings.accounting_provider_name` change — domain, application
and presentation layers are untouched.
"""
from __future__ import annotations

from domain.services.accounting_provider import AccountingProvider
from infrastructure.services.accounting.parser_api_provider import (
    ParserApiAccountingProvider,
)
from infrastructure.settings import settings


class _ProviderHolder:
    instance: AccountingProvider | None = None


def get_accounting_provider() -> AccountingProvider:
    """FastAPI dependency — returns the configured provider singleton."""
    if _ProviderHolder.instance is None:
        _ProviderHolder.instance = _build(settings.accounting_provider_name)
    return _ProviderHolder.instance


def set_accounting_provider(provider: AccountingProvider | None) -> None:
    """Override provider (used by tests)."""
    _ProviderHolder.instance = provider


def _build(name: str) -> AccountingProvider:
    if name == "parser_api":
        return ParserApiAccountingProvider(
            base_url=settings.parser_api_url,
            api_key=settings.parser_api_key,
            timeout_ms=settings.parser_api_timeout_ms,
        )
    raise ValueError(f"Unknown accounting provider: {name!r}")

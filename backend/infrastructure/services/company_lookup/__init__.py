"""Concrete company-lookup provider implementations and factory."""
from __future__ import annotations

from domain.services.company_lookup import CompanyLookupProvider
from infrastructure.services.company_lookup.dadata import DadataCompanyLookupProvider
from infrastructure.settings import settings


class _ProviderState:
    provider: CompanyLookupProvider | None = None


def get_company_lookup_provider() -> CompanyLookupProvider:
    """FastAPI dependency — returns the configured provider singleton.

    Swapping to another provider only requires changing this factory.
    """
    if _ProviderState.provider is None:
        _ProviderState.provider = DadataCompanyLookupProvider(api_key=settings.dadata_api_key)
    return _ProviderState.provider


def set_company_lookup_provider(provider: CompanyLookupProvider | None) -> None:
    """Override provider (used by tests)."""
    _ProviderState.provider = provider

"""Dealer queries (Phase 5 E3 + Phase 7a G4)."""
from application.queries.dealer.get_profile import (
    GetDealerProfileQuery,
    handle_get_dealer_profile,
)
from application.queries.dealer.list_dealer_clients import (
    ListDealerClientsQuery,
    handle_list_dealer_clients,
)

__all__ = [
    "GetDealerProfileQuery",
    "ListDealerClientsQuery",
    "handle_get_dealer_profile",
    "handle_list_dealer_clients",
]

"""Client read-side queries (CQRS)."""
from application.queries.client.get_profile import (
    GetClientProfileQuery,
    handle_get_client_profile,
)
from application.queries.client.list_favorites import (
    ListFavoritesQuery,
    handle_list_favorites,
)
from application.queries.client.list_saved_calculations import (
    ListSavedCalculationsQuery,
    handle_list_saved_calculations,
)

__all__ = [
    "GetClientProfileQuery",
    "ListFavoritesQuery",
    "ListSavedCalculationsQuery",
    "handle_get_client_profile",
    "handle_list_favorites",
    "handle_list_saved_calculations",
]

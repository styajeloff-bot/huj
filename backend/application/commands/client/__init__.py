"""Client commands (profile, favorites, saved calculations, phone change)."""
from application.commands.client.add_favorite import (
    AddFavoriteCommand,
    handle_add_favorite,
)
from application.commands.client.bulk_remove_favorites import (
    BulkRemoveFavoritesCommand,
    handle_bulk_remove_favorites,
)
from application.commands.client.clear_favorites import (
    ClearFavoritesCommand,
    handle_clear_favorites,
)
from application.commands.client.delete_calculation import (
    DeleteSavedCalculationCommand,
    handle_delete_saved_calculation,
)
from application.commands.client.remove_favorite import (
    RemoveFavoriteCommand,
    handle_remove_favorite,
)
from application.commands.client.request_phone_change import (
    RequestPhoneChangeCommand,
    handle_request_phone_change,
)
from application.commands.client.save_calculation import (
    SaveCalculationCommand,
    SaveCalculationResult,
    handle_save_calculation,
)
from application.commands.client.update_profile import (
    UpdateClientProfileCommand,
    handle_update_client_profile,
)
from application.commands.client.verify_phone_change import (
    VerifyPhoneChangeCommand,
    handle_verify_phone_change,
)

__all__ = [
    "AddFavoriteCommand",
    "BulkRemoveFavoritesCommand",
    "ClearFavoritesCommand",
    "DeleteSavedCalculationCommand",
    "RemoveFavoriteCommand",
    "RequestPhoneChangeCommand",
    "SaveCalculationCommand",
    "SaveCalculationResult",
    "UpdateClientProfileCommand",
    "VerifyPhoneChangeCommand",
    "handle_add_favorite",
    "handle_bulk_remove_favorites",
    "handle_clear_favorites",
    "handle_delete_saved_calculation",
    "handle_remove_favorite",
    "handle_request_phone_change",
    "handle_save_calculation",
    "handle_update_client_profile",
    "handle_verify_phone_change",
]

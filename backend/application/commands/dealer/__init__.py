"""Dealer commands (Phase 5 E3).

The dealer cabinet owns three mutation paths:

1. ``invite_client`` — send an SMS invite to a prospective client. If the
   client does not yet have an account, we create one with role ``client``
   and then fire off a verification code via the shared SMS channel.
2. Vehicle create/update — these re-use Phase 2 B1's ``CreateVehicleCommand``
   and ``UpdateVehicleCommand`` directly; dealer scoping is enforced inside
   those handlers (``actor_role == 'dealer'`` coerces ``dealer_id`` to the
   caller and any update requires ownership).
3. List queries live in ``application/queries/dealer``.
"""
from application.commands.dealer.invite_client import (
    InviteClientCommand,
    handle_invite_client,
)
from application.commands.dealer.update_profile import (
    UpdateDealerProfileCommand,
    handle_update_dealer_profile,
)

__all__ = [
    "InviteClientCommand",
    "UpdateDealerProfileCommand",
    "handle_invite_client",
    "handle_update_dealer_profile",
]

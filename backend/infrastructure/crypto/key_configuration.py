"""Startup validation for the shared JWT and Mobile ID key directory."""

from infrastructure.crypto.jwt_keys import install_signing_keys, prepare_signing_keys
from infrastructure.services.mobile_id.keys import (
    configured_mobile_id_kids,
    install_mobile_id_keyset,
    prepare_mobile_id_keyset,
)
from infrastructure.settings import settings


def load_and_validate_key_configuration() -> None:
    """Load the ES256 registry and validate enabled Mobile ID RSA keypairs."""
    try:
        mobile_id_kids = frozenset(configured_mobile_id_kids())
        mobile_id_keyset = prepare_mobile_id_keyset() if settings.mobile_id_enabled else None
        jwt_keys, active_kid = prepare_signing_keys(excluded_kids=mobile_id_kids)
    except (OSError, TypeError, ValueError) as exc:
        msg = f"Invalid shared key configuration: {exc}"
        raise RuntimeError(msg) from exc
    install_signing_keys(jwt_keys, active_kid)
    install_mobile_id_keyset(mobile_id_keyset)

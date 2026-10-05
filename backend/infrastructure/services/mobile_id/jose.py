from __future__ import annotations


class MobileIdJoseUnavailableError(RuntimeError):
    """Production Mobile ID JOSE/JWE operations are intentionally not stubbed."""


def require_production_jose() -> None:
    raise MobileIdJoseUnavailableError(
        "Production Mobile ID JOSE/JWE verification is not implemented"
    )

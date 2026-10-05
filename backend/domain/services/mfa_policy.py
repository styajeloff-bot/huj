"""MFA enforcement policy — which roles must use two-factor auth.

Single source of truth for "is MFA mandatory for this role?". The answer
drives the verify-phone branch: privileged roles without MFA enabled are
forced into a setup flow instead of receiving tokens.

Currently no role is forced; every user enrols MFA voluntarily through
the cabinet toggle. Add a role here to bring back the post-login
``mfaSetupRequired`` short-circuit (e.g. a future ``admin``).
"""
from __future__ import annotations

# Empty by default — MFA is opt-in for all roles. The login flow stops
# inserting an mfaSetupRequired step; users (incl. carcraft_employee)
# enable it themselves from the profile / settings page.
MFA_REQUIRED_ROLES: frozenset[str] = frozenset()


def is_mfa_required(role: str | None) -> bool:
    """Return True iff ``role`` is subject to mandatory MFA enrollment."""
    if not role:
        return False
    return role in MFA_REQUIRED_ROLES


__all__ = ["MFA_REQUIRED_ROLES", "is_mfa_required"]

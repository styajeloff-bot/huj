"""Admin-facing auth helpers (SecOps / support).

After Phase 9 R1 only ``reset-mfa`` lived here; Phase 11 R8 moved it to
``DELETE /api/v1/users/{user_id}/mfa`` for consistency with the
consolidated ``/users/{id}`` admin surface. This module is kept so the
router prefix registration in ``main.py`` stays addressable for any
future admin-auth-only concerns — currently it declares no routes.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

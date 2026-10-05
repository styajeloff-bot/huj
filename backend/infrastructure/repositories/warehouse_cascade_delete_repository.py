"""Warehouse cascade delete repository re-export for compatibility."""
from __future__ import annotations

from infrastructure.repositories.warehouse_cascade_repository import (
    execute_warehouse_cascade_delete,
    get_warehouse_cascade_preview,
    get_warehouse_delete_preview,
)

__all__ = [
    "execute_warehouse_cascade_delete",
    "get_warehouse_cascade_preview",
    "get_warehouse_delete_preview",
]

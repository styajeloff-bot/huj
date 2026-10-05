"""ClickHouse client singleton for DWH / analytics reads and writes.

Re-exports from the sibling ``clickhouse.py`` module file. Python resolves
``from infrastructure.clickhouse import ...`` to this package directory
instead of the ``.py`` file when both exist, so we forward everything.
"""
from __future__ import annotations

# Use spec_from_file_location to load the sibling .py file directly
import importlib.util
import sys
from pathlib import Path

_MODULE_FILE = Path(__file__).resolve().parent.parent / "clickhouse.py"
_SPEC = importlib.util.spec_from_file_location(
    "infrastructure._clickhouse_module", _MODULE_FILE
)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover
    raise ImportError(f"Cannot load {_MODULE_FILE}")

_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["infrastructure._clickhouse_module"] = _MOD
_SPEC.loader.exec_module(_MOD)

ensure_tables = _MOD.ensure_tables
execute_clickhouse = _MOD.execute_clickhouse
execute_clickhouse_batch = _MOD.execute_clickhouse_batch
execute_clickhouse_batch_strict = _MOD.execute_clickhouse_batch_strict
execute_clickhouse_strict = _MOD.execute_clickhouse_strict
get_clickhouse_client = _MOD.get_clickhouse_client
set_clickhouse_client = _MOD.set_clickhouse_client

__all__ = [
    "ensure_tables",
    "execute_clickhouse",
    "execute_clickhouse_batch",
    "execute_clickhouse_batch_strict",
    "execute_clickhouse_strict",
    "get_clickhouse_client",
    "set_clickhouse_client",
]

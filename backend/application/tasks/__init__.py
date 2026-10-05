"""Taskiq task definitions.

Each module here declares one or more ``@broker.task`` functions with a
cron schedule label. Importing this package registers every task against
:data:`infrastructure.taskiq_broker.broker`, which is what the taskiq
worker and scheduler processes bind to.

Tasks own their own ``AsyncSession`` and commit explicitly — the worker
process does not run an ASGI lifespan, so there is no request-scoped
session to reuse.
"""

# Re-exported so that `taskiq worker application.tasks` auto-discovers
# every decorated task regardless of submodule layout.
from application.tasks import (
    compensations,
    data_import,
    document_registry,
    dwh_batches,
    lca_status_history,
    magic_links,
    notifications,
    observability,
    payments,
    sopd,
    special_equipment_import,
    special_equipment_registry,
)

__all__ = [
    "compensations",
    "data_import",
    "document_registry",
    "dwh_batches",
    "lca_status_history",
    "magic_links",
    "notifications",
    "observability",
    "payments",
    "sopd",
    "special_equipment_import",
    "special_equipment_registry",
]

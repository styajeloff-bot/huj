"""SQLAlchemy declarative base for all ORM models."""

import importlib

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""


# Import all models so SQLAlchemy registers them with Base.metadata.
# Without this, ForeignKey references between models in different files
# may fail at flush time (e.g. vehicles.distributor_id -> distributors.id).
_MODULES = (
    "accounting",
    "accounting_metadata",
    "accounting_normalized",
    "bank_statements",
    "applications",
    "catalog",
    "catalog_import_jobs",
    "cart_transfers",
    "citizenship",
    "company_change_history",
    "companies",
    "compensations",
    "contractors",
    "documents",
    "document_registry",
    "email_preferences",
    "exchange",
    "fast_deals",
    "import_jobs",
    "idempotency",
    "lca_status_history",
    "misc",
    "monetization",
    "notification_delivery",
    "payments",
    "positions",
    "questionnaire_dictionaries",
    "questionnaire_settings",
    "section_visibility",
    "signature_requests",
    "special_equipment",
    "special_equipment_commerce",
    "special_equipment_import",
    "special_equipment_registry",
    "storefront_pages",
    "storefronts",
    "sopd_cache",
    "sopd_operator_snapshots",
    "sopd_passport_snapshots",
    "sopd_revocations",
    "support",
    "users",
    "user_company_access",
    "vehicle_deletion_jobs",
    "vehicles",
)

for _mod in _MODULES:
    globals()[_mod] = importlib.import_module(f"infrastructure.models.{_mod}")

__all__ = [
    "Base",
    "accounting",
    "accounting_metadata",
    "accounting_normalized",
    "applications",
    "bank_statements",
    "cart_transfers",
    "catalog",
    "catalog_import_jobs",
    "citizenship",
    "companies",
    "company_change_history",
    "compensations",
    "contractors",
    "document_registry",
    "documents",
    "email_preferences",
    "exchange",
    "fast_deals",
    "idempotency",
    "import_jobs",
    "lca_status_history",
    "misc",
    "monetization",
    "notification_delivery",
    "payments",
    "positions",
    "questionnaire_dictionaries",
    "questionnaire_settings",
    "section_visibility",
    "signature_requests",
    "sopd_cache",
    "sopd_operator_snapshots",
    "sopd_passport_snapshots",
    "sopd_revocations",
    "special_equipment",
    "special_equipment_commerce",
    "special_equipment_import",
    "special_equipment_registry",
    "storefront_pages",
    "storefronts",
    "support",
    "user_company_access",
    "users",
    "vehicle_deletion_jobs",
    "vehicles",
]

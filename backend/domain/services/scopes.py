"""Role-to-scope mapping — single source of truth for authorization scopes.

Scope-based authorization replaces the flat role check. Access tokens carry a
``scopes: list[str]`` claim derived from the user's role via
``roles_to_scopes``. Routers declare the scopes each endpoint requires via
``require_scopes(...)`` instead of listing roles directly.

This module is intentionally dependency-free: the domain layer may not import
from application, infrastructure, or presentation.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Scope taxonomy
#
# Scopes are "<resource>:<action>" strings. Actions are:
#   read  — read/query endpoints
#   write — create/update/delete endpoints
#
# Keep this list in sync with what require_scopes(...) calls the routers use.
# ---------------------------------------------------------------------------

# Purchases domain — order creation, payment, cancellation, schedule.
# Read access to purchase data (list, detail, schedule, payments).
PURCHASES_READ = "purchases:read"
# Create purchase orders. Both clients and employees may create orders
# (employees on behalf of a process).
PURCHASES_WRITE = "purchases:write"
# Client-only self-service writes: create-payment (remaining/scheduled),
# request-cancellation — actions a client takes on their own order.
PURCHASES_SELF_PAY = "purchases:self-pay"
# Employee-only: approving a cancellation request submitted by a client.
PURCHASES_ADMIN = "purchases:admin"

# Catalog ingestion (Excel upload) — employee-only.
CATALOG_WRITE = "catalog:write"

# Isolated special-equipment import resources. These are deliberately not
# granted to distributors through the legacy catalog upload scope.
SPECIAL_EQUIPMENT_IMPORTS_READ = "special-equipment-imports:read"
SPECIAL_EQUIPMENT_IMPORTS_WRITE = "special-equipment-imports:write"
SPECIAL_EQUIPMENT_IMPORTS_APPLY = "special-equipment-imports:apply"

# Operational special-equipment catalog registry.  These scopes are separate
# from both the public read-only catalog and the XLSX import workflow: an
# employee may be allowed to inspect/edit catalog records without gaining the
# ability to apply a bulk import (and vice versa).
SPECIAL_EQUIPMENT_CATALOG_READ = "special-equipment-catalog:read"
SPECIAL_EQUIPMENT_CATALOG_WRITE = "special-equipment-catalog:write"

# Compensations registry.
COMPENSATIONS_READ = "compensations:read"
COMPENSATIONS_WRITE = "compensations:write"
# Employee-only: bulk-cancel support compensations.
COMPENSATIONS_ADMIN = "compensations:admin"

# Notifications — employee can create, users can read/mark their own.
NOTIFICATIONS_READ = "notifications:read"
NOTIFICATIONS_WRITE = "notifications:write"

# Vehicle image writes (public read — no scope needed).
CAR_IMAGES_WRITE = "car-images:write"

# Accounting reports by INN.
ACCOUNTING_READ = "accounting:read"
ACCOUNTING_WRITE = "accounting:write"

# Email preferences — always self-scoped, any authenticated user.
EMAIL_PREFERENCES_READ = "email-preferences:read"
EMAIL_PREFERENCES_WRITE = "email-preferences:write"
# Admin-only email tooling: send-test, stats, logs. Employee-only.
EMAIL_PREFERENCES_ADMIN = "email-preferences:admin"

# Company lookup — any authenticated user.
COMPANY_LOOKUP_READ = "company-lookup:read"

# Auth administration — session inspection, force-logout, enable/disable
# of any user. SecOps / support surface; reserved for employees only.
AUTH_ADMIN = "auth:admin"

# Support-program administration — CRUD over support programs,
# dealer groups and bill-of-lading uploads. Employee-only.
SUPPORT_ADMIN = "support:admin"

# Warehouses — role-scoped read access. Employees see every warehouse,
# distributors see linked dealers' warehouses, and dealers see their own.
WAREHOUSES_READ = "warehouses:read"

# Warehouses & cities administration — CRUD over warehouses, cities and
# vehicle-warehouse bindings. Granted to employees and distributors.
WAREHOUSES_ADMIN = "warehouses:admin"

# Dealer options — global reference list of extra dealer services.
# Read access is granted to dealers + employees (dealers need it to
# pick options for exchange bids); write access is employee-only.
DEALER_OPTIONS_READ = "dealer-options:read"
DEALER_OPTIONS_WRITE = "dealer-options:write"

# Vehicles administration — admin CRUD over the vehicle inventory.
# Granted to carcraft employees and dealers (dealers may only manage
# their own vehicles — ownership is enforced inside the handler via
# `dealer_id`). Distributor read-access is granted as well so that
# distributor-side admin views may inspect the vehicle inventory.
VEHICLES_ADMIN = "vehicles:admin"

# Featured vehicles administration — homepage curation. Employee-only.
# Also gates the application-vehicle assignment helpers (assign vehicle
# to dealer / assign VIN / list available VINs) which are part of the
# distribution workflow run by carcraft staff.
FEATURED_ADMIN = "featured:admin"

# Catalog storefront configuration and branding. Employee-only.
STOREFRONTS_ADMIN = "storefronts:admin"

# Leasing applications domain (Phase 3) — clients/dealers create and read
# their own applications, leasing companies see those they have been
# selected on, employees see all. Owner / role visibility is enforced
# inside handlers via the LeasingApplication aggregate root.
APPLICATIONS_READ = "applications:read"
APPLICATIONS_WRITE = "applications:write"

# Leasing-company review workflow (Phase 4 — D3).
# Required to approve / reject / request-documents on a submitted
# application from the LC cabinet. Granted to ``leasing_company`` and
# ``carcraft_employee``; no other role may drive the LC review workflow.
LEASING_REVIEW = "leasing:review"

# Documents domain (Phase 4 — D1).
# READ — list/get/download documents. Granted to anyone who may have a
#     reason to see their own documents or the documents of an application
#     they are part of (clients, dealers, leasing_company reviewers,
#     employees).
# WRITE — upload + version upload. Granted to document owners (clients /
#     dealers) and carcraft_employee. Leasing companies do NOT upload.
# REVIEW — change document status (approve / reject / request revision).
#     Employee-only here; D2 owns LC-side reviews via a separate path.
DOCUMENTS_READ = "documents:read"
DOCUMENTS_WRITE = "documents:write"
DOCUMENTS_REVIEW = "documents:review"

# Exchange domain (Phase 5 — E2) — биржа транспортных средств.
# READ — list/detail of exchange requests, bids and cart. Granted to
#     leasing_company, dealer and carcraft_employee.
# WRITE — create/update exchange requests, bids and cart mutations.
#     Granted to leasing_company (requests + cart + approve/reject bids),
#     dealer (bid CRUD), and employees (oversight).
EXCHANGE_READ = "exchange:read"
EXCHANGE_WRITE = "exchange:write"

# Reports domain (Phase 6 — F1) — read-only reporting / analytics / exports.
# READ — role-scoped access: dealers see their own, LC sees theirs, distributor
#     sees theirs, employees see everything. Ownership filtering is applied
#     inside the query handlers.
# ADMIN — admin-only analytics (top-level dashboard, aggregate analytics).
#     Employee-only.
REPORTS_READ = "reports:read"
REPORTS_ADMIN = "reports:admin"

# Admin domain (Phase 6 — F2) — residual admin endpoints that were not
# covered by earlier phases (warehouses/cities/support/featured/...):
#   * users CRUD (``users:admin``),
#   * companies create (``companies:admin``),
#   * platform stats + leasing-companies / dealers directories
#     (``admin-stats:read``),
#   * admin-side leasing application listing + LC assignment
#     (``admin-applications:write``).
# All are employee-only.
USERS_ADMIN = "users:admin"
COMPANIES_ADMIN = "companies:admin"
ADMIN_STATS_READ = "admin-stats:read"
ADMIN_APPLICATIONS = "admin-applications:write"


# ---------------------------------------------------------------------------
# Role → scope mapping
#
# Roles mirror infrastructure/models/enums.py::USER_ROLES:
#   client, carcraft_employee, dealer, leasing_company, distributor
# ---------------------------------------------------------------------------

_CLIENT_SCOPES: frozenset[str] = frozenset(
    {
        PURCHASES_READ,
        PURCHASES_WRITE,
        PURCHASES_SELF_PAY,
        COMPENSATIONS_READ,
        NOTIFICATIONS_READ,
        ACCOUNTING_READ,
        ACCOUNTING_WRITE,
        EMAIL_PREFERENCES_READ,
        EMAIL_PREFERENCES_WRITE,
        COMPANY_LOOKUP_READ,
        APPLICATIONS_READ,
        APPLICATIONS_WRITE,
        DOCUMENTS_READ,
        DOCUMENTS_WRITE,
        REPORTS_READ,
    }
)

_EMPLOYEE_SCOPES: frozenset[str] = frozenset(
    {
        PURCHASES_READ,
        PURCHASES_WRITE,
        PURCHASES_ADMIN,
        CATALOG_WRITE,
        SPECIAL_EQUIPMENT_IMPORTS_READ,
        SPECIAL_EQUIPMENT_IMPORTS_WRITE,
        SPECIAL_EQUIPMENT_IMPORTS_APPLY,
        SPECIAL_EQUIPMENT_CATALOG_READ,
        SPECIAL_EQUIPMENT_CATALOG_WRITE,
        COMPENSATIONS_READ,
        COMPENSATIONS_WRITE,
        COMPENSATIONS_ADMIN,
        NOTIFICATIONS_READ,
        NOTIFICATIONS_WRITE,
        CAR_IMAGES_WRITE,
        ACCOUNTING_READ,
        ACCOUNTING_WRITE,
        EMAIL_PREFERENCES_READ,
        EMAIL_PREFERENCES_WRITE,
        EMAIL_PREFERENCES_ADMIN,
        COMPANY_LOOKUP_READ,
        AUTH_ADMIN,
        SUPPORT_ADMIN,
        WAREHOUSES_READ,
        WAREHOUSES_ADMIN,
        DEALER_OPTIONS_READ,
        DEALER_OPTIONS_WRITE,
        VEHICLES_ADMIN,
        FEATURED_ADMIN,
        STOREFRONTS_ADMIN,
        APPLICATIONS_READ,
        APPLICATIONS_WRITE,
        DOCUMENTS_READ,
        DOCUMENTS_WRITE,
        DOCUMENTS_REVIEW,
        LEASING_REVIEW,
        EXCHANGE_READ,
        EXCHANGE_WRITE,
        REPORTS_READ,
        REPORTS_ADMIN,
        USERS_ADMIN,
        COMPANIES_ADMIN,
        ADMIN_STATS_READ,
        ADMIN_APPLICATIONS,
    }
)

_DEALER_SCOPES: frozenset[str] = frozenset(
    {
        COMPENSATIONS_READ,
        COMPENSATIONS_WRITE,
        NOTIFICATIONS_READ,
        ACCOUNTING_READ,
        EMAIL_PREFERENCES_READ,
        EMAIL_PREFERENCES_WRITE,
        COMPANY_LOOKUP_READ,
        DEALER_OPTIONS_READ,
        VEHICLES_ADMIN,
        WAREHOUSES_READ,
        WAREHOUSES_ADMIN,
        APPLICATIONS_READ,
        APPLICATIONS_WRITE,
        DOCUMENTS_READ,
        DOCUMENTS_WRITE,
        EXCHANGE_READ,
        EXCHANGE_WRITE,
        REPORTS_READ,
    }
)

_DISTRIBUTOR_SCOPES: frozenset[str] = frozenset(
    {
        EXCHANGE_READ,
        COMPENSATIONS_READ,
        COMPENSATIONS_WRITE,
        NOTIFICATIONS_READ,
        ACCOUNTING_READ,
        EMAIL_PREFERENCES_READ,
        EMAIL_PREFERENCES_WRITE,
        COMPANY_LOOKUP_READ,
        VEHICLES_ADMIN,
        APPLICATIONS_READ,
        APPLICATIONS_WRITE,
        REPORTS_READ,
        # Admin-equivalent scopes: distributor gets the same support,
        # catalog-upload and warehouse-management panels as carcraft_employee.
        SUPPORT_ADMIN,
        WAREHOUSES_READ,
        WAREHOUSES_ADMIN,
        CATALOG_WRITE,
    }
)

_LEASING_COMPANY_SCOPES: frozenset[str] = frozenset(
    {
        COMPENSATIONS_READ,
        NOTIFICATIONS_READ,
        ACCOUNTING_READ,
        EMAIL_PREFERENCES_READ,
        EMAIL_PREFERENCES_WRITE,
        COMPANY_LOOKUP_READ,
        APPLICATIONS_READ,
        DOCUMENTS_READ,
        # D2 — LC reviewers request documents and review uploads.
        DOCUMENTS_REVIEW,
        # D3 — approve / reject / request-documents for submitted applications.
        LEASING_REVIEW,
        # E2 — exchange subsystem: LC owns requests and cart, approves bids.
        EXCHANGE_READ,
        EXCHANGE_WRITE,
        # LC picks dealer options to attach to an exchange request — needs read.
        DEALER_OPTIONS_READ,
        REPORTS_READ,
    }
)

# External-API integrations get an empty scope set by default — the
# operator grants per-token permissions explicitly when minting an API
# key, otherwise scope-gated endpoints refuse to serve the request.
# Bearer-header tokens are gated to this role at the auth dependency.
_EXTERNAL_API_SCOPES: frozenset[str] = frozenset()


_ROLE_SCOPES: dict[str, frozenset[str]] = {
    "client": _CLIENT_SCOPES,
    "carcraft_employee": _EMPLOYEE_SCOPES,
    "dealer": _DEALER_SCOPES,
    "distributor": _DISTRIBUTOR_SCOPES,
    "leasing_company": _LEASING_COMPANY_SCOPES,
    "external_api": _EXTERNAL_API_SCOPES,
}


def roles_to_scopes(role: str | None) -> list[str]:
    """Return the sorted list of scopes granted to ``role``.

    Unknown / missing roles resolve to an empty list — the token still
    authenticates the user, but no scope-gated endpoint will allow access.
    """
    if not role:
        return []
    return sorted(_ROLE_SCOPES.get(role, frozenset()))


def has_all_scopes(user_scopes: list[str] | None, required: tuple[str, ...]) -> bool:
    """Return True iff ``user_scopes`` covers every entry in ``required``."""
    if not required:
        return True
    if not user_scopes:
        return False
    granted = set(user_scopes)
    return all(scope in granted for scope in required)

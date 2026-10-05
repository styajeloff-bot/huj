"""Allow storefront application sources in monetization and index applications."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "137"
down_revision = "136"
branch_labels = None
depends_on = None

_SOURCE_TYPES = "'platform','dealer_account','exchange'"
_APPLICATION_TYPES = "'platform','dealer_account'"
_SITE_TYPES = "'dealer_site','distributor_site'"


def _replace_constraints(*, include_sites: bool) -> None:
    sources = _SOURCE_TYPES + ("," + _SITE_TYPES if include_sites else "")
    applications = _APPLICATION_TYPES + ("," + _SITE_TYPES if include_sites else "")
    op.drop_constraint(
        "ck_monetization_source_type", "monetization_program_sources", type_="check"
    )
    op.create_check_constraint(
        "ck_monetization_source_type",
        "monetization_program_sources",
        f"source_type IN ({sources})",
    )
    op.drop_constraint(
        "ck_monetization_deal_origin", "monetization_deals", type_="check"
    )
    op.create_check_constraint(
        "ck_monetization_deal_origin",
        "monetization_deals",
        "(exchange_request_id IS NOT NULL AND application_id IS NULL "
        "AND leasing_company_application_id IS NULL AND source_type = 'exchange') "
        "OR (exchange_request_id IS NULL AND application_id IS NOT NULL "
        "AND leasing_company_application_id IS NOT NULL "
        f"AND source_type IN ({applications}))",
    )


def upgrade() -> None:
    op.create_index(
        "idx_leasing_applications_source_type", "leasing_applications", ["source_type"]
    )
    _replace_constraints(include_sites=True)


def downgrade() -> None:
    site_data_exists = op.get_bind().execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM monetization_program_sources "
            "WHERE source_type IN ('dealer_site', 'distributor_site')) "
            "OR EXISTS (SELECT 1 FROM monetization_deals "
            "WHERE source_type IN ('dealer_site', 'distributor_site'))"
        )
    ).scalar()
    if site_data_exists:
        raise RuntimeError(
            "Cannot remove storefront sources while monetization data uses them"
        )
    _replace_constraints(include_sites=False)
    op.drop_index(
        "idx_leasing_applications_source_type", table_name="leasing_applications"
    )

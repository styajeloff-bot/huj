"""Fast deal registration: own aggregate, global claims and monetization sources.

Revision ID: 168
Revises: 167

Creates the eight ``fast_deal*`` tables and widens the shared tables that must
recognise the new source: allocations (global reserve), applied supports,
compensations, monetization sources/deals and the claimed-price rule of catalog
products. Existing numbers, statuses and snapshots are untouched.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "168"
down_revision = "167"
branch_labels = None
depends_on = None

_DEAL_STATUSES = (
    "draft",
    "pending_lc_confirmation",
    "pending_lc_final_confirmation",
    "pending_dealer_confirmation",
    "pending_lc_changes_confirmation",
    "confirmed",
    "rejected",
    "cancelled",
)
_LC_STATUSES = (
    "pending_review",
    "offer_sent",
    "selected_by_dealer",
    "confirmed",
    "rejected",
    "closed_not_selected",
)
_FILE_KINDS = ("deal_main", "deal_additional", "lc_offer_pdf", "vehicle_offer")
_SUPPORT_STATUSES = ("requested", "pre_approved", "approved", "cancelled")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def _pk() -> sa.Column:
    return sa.Column(
        "id",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _uuid(name: str, target: str | None = None, *, nullable: bool = True,
          ondelete: str = "RESTRICT") -> sa.Column:
    if target is None:
        return sa.Column(name, UUID(as_uuid=True), nullable=nullable)
    return sa.Column(
        name, UUID(as_uuid=True), sa.ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
    )


def _now(name: str = "created_at") -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def upgrade() -> None:
    _create_fast_deals()
    _create_fast_deal_vehicles()
    _create_lc_applications()
    _create_files()
    _create_offers()
    _create_history()
    _create_support_requests()
    _create_assignees()
    op.create_foreign_key(
        "fk_fast_deals_final_offer", "fast_deals", "fast_deal_offers",
        ["final_offer_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_fast_deal_lc_applications_current_offer", "fast_deal_lc_applications",
        "fast_deal_offers", ["current_offer_id"], ["id"], ondelete="RESTRICT",
    )
    _guard_offer_immutability()
    _extend_allocations()
    _extend_applied_supports()
    _extend_compensations()
    _extend_monetization()
    _relax_claimed_price()


def _create_fast_deals() -> None:
    op.create_table(
        "fast_deals",
        _pk(),
        sa.Column("display_number", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(40), nullable=False,
                  server_default=sa.text("'draft'")),
        sa.Column("group_id", UUID(as_uuid=True), nullable=True),
        _uuid("client_company_id", "companies.id", nullable=False),
        sa.Column("client_phone", sa.String(16), nullable=False),
        _uuid("initiator_company_id", "companies.id", nullable=False),
        _uuid("created_by", "users.id", nullable=False),
        _uuid("dealer_company_id", "companies.id"),
        _uuid("leasing_company_id", "companies.id"),
        sa.Column("final_offer_id", UUID(as_uuid=True), nullable=True),
        sa.Column("down_payment_mode", sa.String(10), nullable=True),
        sa.Column("down_payment", sa.Numeric(15, 2), nullable=True),
        sa.Column("down_payment_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("lease_term_months", sa.Integer, nullable=True),
        sa.Column("monthly_payment", sa.Numeric(15, 2), nullable=True),
        sa.Column("monthly_payment_is_manual", sa.Boolean, nullable=False,
                  server_default=sa.false()),
        sa.Column("calculated_monthly_payment", sa.Numeric(15, 2), nullable=True),
        sa.Column("buyout_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("calc_snapshot", JSONB, nullable=True),
        sa.Column("vehicles_total", sa.Numeric(15, 2), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("final_total_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("final_down_payment", sa.Numeric(15, 2), nullable=True),
        sa.Column("final_down_payment_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("final_lease_term_months", sa.Integer, nullable=True),
        sa.Column("final_monthly_payment", sa.Numeric(15, 2), nullable=True),
        sa.Column("final_total_cost", sa.Numeric(15, 2), nullable=True),
        sa.Column("final_buyout_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("has_pending_changes", sa.Boolean, nullable=False,
                  server_default=sa.false()),
        sa.Column("sent_snapshot", JSONB, nullable=True),
        sa.Column("confirmed_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("status_reason", sa.Text, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("review_cycle", sa.Integer, nullable=False,
                  server_default=sa.text("1")),
        _ts("sent_at"),
        _ts("confirmed_at"),
        _ts("rejected_at"),
        _ts("cancelled_at"),
        _now("created_at"),
        _now("updated_at"),
        sa.UniqueConstraint("display_number", name="uq_fast_deals_display_number"),
        sa.CheckConstraint(
            "source_type IN ('dealer_to_leasing', 'leasing_to_dealer')",
            name="ck_fast_deals_source_type",
        ),
        sa.CheckConstraint(_in_list("status", _DEAL_STATUSES), name="ck_fast_deals_status"),
        sa.CheckConstraint(
            "down_payment_mode IS NULL OR down_payment_mode IN ('amount', 'percent')",
            name="ck_fast_deals_down_payment_mode",
        ),
        sa.CheckConstraint(
            "lease_term_months IS NULL OR lease_term_months BETWEEN 12 AND 84",
            name="ck_fast_deals_lease_term",
        ),
        sa.CheckConstraint(
            "final_lease_term_months IS NULL OR final_lease_term_months BETWEEN 12 AND 84",
            name="ck_fast_deals_final_lease_term",
        ),
        sa.CheckConstraint(
            "(down_payment IS NULL OR down_payment >= 0) "
            "AND (monthly_payment IS NULL OR monthly_payment >= 0) "
            "AND (buyout_amount IS NULL OR buyout_amount >= 0) "
            "AND (calculated_monthly_payment IS NULL OR calculated_monthly_payment >= 0) "
            "AND vehicles_total >= 0 "
            "AND (confirmed_amount IS NULL OR confirmed_amount >= 0)",
            name="ck_fast_deals_amounts_nonnegative",
        ),
        sa.CheckConstraint(
            "(final_total_amount IS NULL OR final_total_amount >= 0) "
            "AND (final_down_payment IS NULL OR final_down_payment >= 0) "
            "AND (final_monthly_payment IS NULL OR final_monthly_payment >= 0) "
            "AND (final_total_cost IS NULL OR final_total_cost >= 0) "
            "AND (final_buyout_amount IS NULL OR final_buyout_amount >= 0)",
            name="ck_fast_deals_final_amounts_nonnegative",
        ),
        sa.CheckConstraint(
            "down_payment_percent IS NULL OR "
            "(down_payment_percent >= 0 AND down_payment_percent <= 100)",
            name="ck_fast_deals_down_payment_percent",
        ),
        sa.CheckConstraint(
            "client_phone ~ '^\\+7[0-9]{10}$'", name="ck_fast_deals_client_phone"
        ),
        sa.CheckConstraint(
            "version >= 1 AND review_cycle >= 1", name="ck_fast_deals_counters"
        ),
        sa.CheckConstraint(
            "source_type <> 'dealer_to_leasing' "
            "OR dealer_company_id = initiator_company_id",
            name="ck_fast_deals_dd_dealer_is_initiator",
        ),
        sa.CheckConstraint(
            "source_type <> 'leasing_to_dealer' "
            "OR leasing_company_id = initiator_company_id",
            name="ck_fast_deals_dl_leasing_is_initiator",
        ),
        sa.CheckConstraint(
            "status <> 'confirmed' OR "
            "(confirmed_amount IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="ck_fast_deals_confirmed_snapshot",
        ),
    )
    op.create_index(
        "idx_fast_deals_initiator_created", "fast_deals",
        ["initiator_company_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "idx_fast_deals_dealer_created", "fast_deals",
        ["dealer_company_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "idx_fast_deals_leasing_created", "fast_deals",
        ["leasing_company_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "idx_fast_deals_client_created", "fast_deals",
        ["client_company_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index("idx_fast_deals_status_source", "fast_deals", ["status", "source_type"])
    op.create_index(
        "idx_fast_deals_group", "fast_deals", ["group_id"],
        postgresql_where=sa.text("group_id IS NOT NULL"),
    )
    op.create_index("idx_fast_deals_created_by", "fast_deals", ["created_by"])
    op.create_index(
        "idx_fast_deals_created_at", "fast_deals",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )


def _create_fast_deal_vehicles() -> None:
    op.create_table(
        "fast_deal_vehicles",
        _pk(),
        _uuid("fast_deal_id", "fast_deals.id", nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default=sa.text("0")),
        _uuid("product_id", "special_equipment_products.id", ondelete="SET NULL"),
        sa.Column("vehicle_source_type", sa.String(16), nullable=False),
        _uuid("mark_id", "special_equipment_marks.id", ondelete="SET NULL"),
        _uuid("model_id", "special_equipment_models.id", ondelete="SET NULL"),
        _uuid("modification_id", "special_equipment_modifications.id", ondelete="SET NULL"),
        _uuid("trim_id", "special_equipment_trims.id", ondelete="SET NULL"),
        _uuid("category_id", "special_equipment_categories.id", ondelete="SET NULL"),
        _uuid("body_color_id", "special_equipment_colors.id", ondelete="SET NULL"),
        sa.Column("body_color_name", sa.String(255), nullable=True),
        sa.Column("mark_name", sa.String(255), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("modification_name", sa.String(255), nullable=True),
        sa.Column("trim_name", sa.String(255), nullable=True),
        sa.Column("category_name", sa.String(255), nullable=True),
        sa.Column("vin", sa.String(32), nullable=False),
        sa.Column("vin_entered_manually", sa.Boolean, nullable=False,
                  server_default=sa.false()),
        sa.Column("is_reservable", sa.Boolean, nullable=False, server_default=sa.false()),
        _uuid("warehouse_id", "warehouses.id", ondelete="SET NULL"),
        _uuid("dealer_company_id", "companies.id"),
        sa.Column("base_price", sa.Numeric(15, 2), nullable=False),
        sa.Column("adjustment_type", sa.String(16), nullable=True),
        sa.Column("adjustment_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("equipments", JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("services", JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("purposes", JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("regions", JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("support_amount", sa.Numeric(15, 2), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("options_amount", sa.Numeric(15, 2), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("final_price", sa.Numeric(15, 2), nullable=False),
        sa.Column("item_status", sa.String(16), nullable=False,
                  server_default=sa.text("'active'")),
        _uuid("replaced_by_id", "fast_deal_vehicles.id"),
        sa.Column("catalog_snapshot", JSONB, nullable=True),
        _uuid("created_by", "users.id", nullable=False),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint(
            "vehicle_source_type IN ('product', 'manual')",
            name="ck_fast_deal_vehicles_source_type",
        ),
        sa.CheckConstraint(
            "item_status IN ('active', 'removed', 'replaced')",
            name="ck_fast_deal_vehicles_item_status",
        ),
        sa.CheckConstraint(
            "base_price >= 0 AND final_price >= 0 AND support_amount >= 0 "
            "AND options_amount >= 0",
            name="ck_fast_deal_vehicles_amounts",
        ),
        sa.CheckConstraint(
            "(adjustment_type IS NULL AND adjustment_amount IS NULL) OR "
            "(adjustment_type IN ('discount', 'markup') "
            "AND adjustment_amount IS NOT NULL AND adjustment_amount > 0)",
            name="ck_fast_deal_vehicles_adjustment",
        ),
        sa.CheckConstraint(
            "replaced_by_id IS NULL OR item_status = 'replaced'",
            name="ck_fast_deal_vehicles_replaced_by",
        ),
        sa.CheckConstraint(
            "NOT is_reservable OR (vehicle_source_type = 'product' "
            "AND product_id IS NOT NULL AND NOT vin_entered_manually)",
            name="ck_fast_deal_vehicles_reservable",
        ),
    )
    op.create_index(
        "uq_fast_deal_vehicles_active_vin", "fast_deal_vehicles",
        ["fast_deal_id", "vin"], unique=True,
        postgresql_where=sa.text("item_status = 'active'"),
    )
    op.create_index(
        "uq_fast_deal_vehicles_active_product", "fast_deal_vehicles",
        ["fast_deal_id", "product_id"], unique=True,
        postgresql_where=sa.text("item_status = 'active' AND product_id IS NOT NULL"),
    )
    op.create_index(
        "idx_fast_deal_vehicles_deal", "fast_deal_vehicles", ["fast_deal_id", "position"]
    )
    op.create_index(
        "idx_fast_deal_vehicles_product", "fast_deal_vehicles", ["product_id"],
        postgresql_where=sa.text("product_id IS NOT NULL"),
    )
    op.create_index(
        "idx_fast_deal_vehicles_dealer", "fast_deal_vehicles", ["dealer_company_id"]
    )


def _create_lc_applications() -> None:
    op.create_table(
        "fast_deal_lc_applications",
        _pk(),
        _uuid("fast_deal_id", "fast_deals.id", nullable=False),
        _uuid("leasing_company_id", "companies.id", nullable=False),
        sa.Column("status", sa.String(32), nullable=False,
                  server_default=sa.text("'pending_review'")),
        sa.Column("current_offer_id", UUID(as_uuid=True), nullable=True),
        sa.Column("review_cycle", sa.Integer, nullable=False,
                  server_default=sa.text("1")),
        _ts("archived_at"),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        _ts("selected_at"),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint(
            _in_list("status", _LC_STATUSES), name="ck_fast_deal_lc_applications_status"
        ),
        sa.CheckConstraint("review_cycle >= 1", name="ck_fast_deal_lc_applications_cycle"),
    )
    op.create_index(
        "uq_fast_deal_lc_applications_active", "fast_deal_lc_applications",
        ["fast_deal_id", "leasing_company_id"], unique=True,
        postgresql_where=sa.text("archived_at IS NULL AND status <> 'rejected'"),
    )
    op.create_index(
        "idx_fast_deal_lc_applications_deal", "fast_deal_lc_applications",
        ["fast_deal_id", "review_cycle"],
    )
    op.create_index(
        "idx_fast_deal_lc_applications_company", "fast_deal_lc_applications",
        ["leasing_company_id", "status", sa.text("created_at DESC")],
    )


def _create_files() -> None:
    op.create_table(
        "fast_deal_files",
        _pk(),
        _uuid("fast_deal_id", "fast_deals.id", nullable=False),
        _uuid("fast_deal_vehicle_id", "fast_deal_vehicles.id"),
        _uuid("lc_application_id", "fast_deal_lc_applications.id"),
        sa.Column("kind", sa.String(24), nullable=False),
        _uuid("addressee_company_id", "companies.id"),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        _uuid("uploaded_by", "users.id", nullable=False),
        _uuid("uploaded_by_company_id", "companies.id", nullable=False),
        _now("created_at"),
        sa.CheckConstraint(_in_list("kind", _FILE_KINDS), name="ck_fast_deal_files_kind"),
        sa.CheckConstraint("size_bytes > 0", name="ck_fast_deal_files_size"),
        sa.CheckConstraint(
            "(kind = 'vehicle_offer') = (fast_deal_vehicle_id IS NOT NULL)",
            name="ck_fast_deal_files_vehicle_link",
        ),
        sa.CheckConstraint(
            "kind <> 'deal_main' OR addressee_company_id IS NULL",
            name="ck_fast_deal_files_main_unaddressed",
        ),
        sa.CheckConstraint(
            "kind <> 'deal_additional' OR addressee_company_id IS NOT NULL",
            name="ck_fast_deal_files_additional_addressed",
        ),
        sa.CheckConstraint(
            "kind NOT IN ('lc_offer_pdf', 'vehicle_offer') OR lc_application_id IS NOT NULL",
            name="ck_fast_deal_files_lc_link",
        ),
    )
    op.create_index("idx_fast_deal_files_deal", "fast_deal_files", ["fast_deal_id", "kind"])
    op.create_index(
        "idx_fast_deal_files_addressee", "fast_deal_files", ["addressee_company_id"],
        postgresql_where=sa.text("addressee_company_id IS NOT NULL"),
    )
    op.create_index("idx_fast_deal_files_storage_key", "fast_deal_files", ["storage_key"])


def _create_offers() -> None:
    op.create_table(
        "fast_deal_offers",
        _pk(),
        _uuid("lc_application_id", "fast_deal_lc_applications.id", nullable=False),
        sa.Column("review_cycle", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("total_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("down_payment", sa.Numeric(15, 2), nullable=False),
        sa.Column("down_payment_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("lease_term_months", sa.Integer, nullable=False),
        sa.Column("monthly_payment", sa.Numeric(15, 2), nullable=False),
        sa.Column("total_cost", sa.Numeric(15, 2), nullable=False),
        sa.Column("buyout_amount", sa.Numeric(15, 2), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("markup", sa.Numeric(15, 2), nullable=True),
        sa.Column("total_interest", sa.Numeric(15, 2), nullable=True),
        sa.Column("vat_refund", sa.Numeric(15, 2), nullable=True),
        sa.Column("profit_tax_savings", sa.Numeric(15, 2), nullable=True),
        sa.Column("total_savings", sa.Numeric(15, 2), nullable=True),
        sa.Column("optional_financial_terms", JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        _uuid("pdf_file_id", "fast_deal_files.id"),
        _uuid("created_by", "users.id", nullable=False),
        _now("created_at"),
        _ts("superseded_at"),
        sa.CheckConstraint(
            "lease_term_months BETWEEN 12 AND 84", name="ck_fast_deal_offers_lease_term"
        ),
        sa.CheckConstraint(
            "total_amount >= 0 AND down_payment >= 0 AND monthly_payment >= 0 "
            "AND total_cost >= 0 AND buyout_amount >= 0",
            name="ck_fast_deal_offers_amounts",
        ),
    )
    op.create_index(
        "idx_fast_deal_offers_lc_application", "fast_deal_offers", ["lc_application_id"]
    )


def _create_history() -> None:
    op.create_table(
        "fast_deal_status_history",
        _pk(),
        _uuid("fast_deal_id", "fast_deals.id", nullable=False),
        _uuid("lc_application_id", "fast_deal_lc_applications.id"),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("from_status", sa.String(40), nullable=True),
        sa.Column("to_status", sa.String(40), nullable=True),
        _uuid("actor_user_id", "users.id", ondelete="SET NULL"),
        _uuid("actor_company_id", "companies.id", ondelete="SET NULL"),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("changes", JSONB, nullable=True),
        sa.Column("deal_version", sa.Integer, nullable=True),
        sa.Column("review_cycle", sa.Integer, nullable=True),
        _now("created_at"),
    )
    op.create_index(
        "idx_fast_deal_history_deal", "fast_deal_status_history",
        ["fast_deal_id", "created_at", "id"],
    )


def _create_support_requests() -> None:
    op.create_table(
        "fast_deal_support_requests",
        _pk(),
        _uuid("fast_deal_vehicle_id", "fast_deal_vehicles.id", nullable=False),
        _uuid("fast_deal_id", "fast_deals.id", nullable=False),
        _uuid("distributor_company_id", "companies.id", nullable=False),
        sa.Column("requested_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("decided_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("accounted_amount", sa.Numeric(15, 2), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default=sa.text("'requested'")),
        _uuid("requested_by", "users.id", nullable=False),
        _uuid("decided_by", "users.id", ondelete="SET NULL"),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("decision_comment", sa.Text, nullable=True),
        _ts("decided_at"),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint(
            _in_list("status", _SUPPORT_STATUSES),
            name="ck_fast_deal_support_requests_status",
        ),
        sa.CheckConstraint(
            "requested_amount > 0", name="ck_fast_deal_support_requests_requested"
        ),
        sa.CheckConstraint(
            "decided_amount IS NULL OR decided_amount > 0",
            name="ck_fast_deal_support_requests_decided",
        ),
        sa.CheckConstraint(
            "status <> 'approved' OR decided_amount IS NOT NULL",
            name="ck_fast_deal_support_requests_approved_amount",
        ),
        sa.CheckConstraint(
            "accounted_amount >= 0", name="ck_fast_deal_support_requests_accounted"
        ),
    )
    op.create_index(
        "uq_fast_deal_support_requests_open", "fast_deal_support_requests",
        ["fast_deal_vehicle_id"], unique=True,
        postgresql_where=sa.text("status IN ('requested', 'pre_approved')"),
    )
    op.create_index(
        "idx_fast_deal_support_requests_distributor", "fast_deal_support_requests",
        ["distributor_company_id", "status", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_fast_deal_support_requests_deal", "fast_deal_support_requests", ["fast_deal_id"]
    )


def _create_assignees() -> None:
    op.create_table(
        "fast_deal_assignees",
        _pk(),
        _uuid("fast_deal_id", "fast_deals.id", nullable=False),
        _uuid("company_id", "companies.id", nullable=False),
        _uuid("user_id", "users.id", nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        _uuid("assigned_by", "users.id", ondelete="SET NULL"),
        _now("assigned_at"),
        sa.CheckConstraint(
            "role IN ('primary', 'additional')", name="ck_fast_deal_assignees_role"
        ),
        sa.UniqueConstraint(
            "fast_deal_id", "company_id", "role", name="uq_fast_deal_assignees_role"
        ),
        sa.UniqueConstraint(
            "fast_deal_id", "company_id", "user_id", name="uq_fast_deal_assignees_user"
        ),
    )
    op.create_index("idx_fast_deal_assignees_user", "fast_deal_assignees", ["user_id"])


def _guard_offer_immutability() -> None:
    """A sent offer keeps its financial terms; only its lifecycle marks may change."""
    op.execute(
        """
        CREATE FUNCTION fast_deal_offers_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.lc_application_id IS DISTINCT FROM OLD.lc_application_id
             OR NEW.review_cycle IS DISTINCT FROM OLD.review_cycle
             OR NEW.total_amount IS DISTINCT FROM OLD.total_amount
             OR NEW.down_payment IS DISTINCT FROM OLD.down_payment
             OR NEW.down_payment_percent IS DISTINCT FROM OLD.down_payment_percent
             OR NEW.lease_term_months IS DISTINCT FROM OLD.lease_term_months
             OR NEW.monthly_payment IS DISTINCT FROM OLD.monthly_payment
             OR NEW.total_cost IS DISTINCT FROM OLD.total_cost
             OR NEW.buyout_amount IS DISTINCT FROM OLD.buyout_amount
             OR NEW.rate IS DISTINCT FROM OLD.rate
             OR NEW.markup IS DISTINCT FROM OLD.markup
             OR NEW.total_interest IS DISTINCT FROM OLD.total_interest
             OR NEW.vat_refund IS DISTINCT FROM OLD.vat_refund
             OR NEW.profit_tax_savings IS DISTINCT FROM OLD.profit_tax_savings
             OR NEW.total_savings IS DISTINCT FROM OLD.total_savings
             OR NEW.optional_financial_terms IS DISTINCT FROM OLD.optional_financial_terms
             OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN
            RAISE EXCEPTION 'fast_deal_offers financial terms are immutable'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_fast_deal_offers_immutable BEFORE UPDATE ON fast_deal_offers "
        "FOR EACH ROW EXECUTE FUNCTION fast_deal_offers_immutable()"
    )


def _extend_allocations() -> None:
    table = "application_vehicle_allocations"
    op.add_column(table, sa.Column("fast_deal_vehicle_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_allocation_fast_deal_vehicle", table, "fast_deal_vehicles",
        ["fast_deal_vehicle_id"], ["id"], ondelete="RESTRICT",
    )
    op.alter_column(table, "application_vehicle_id", nullable=True)
    op.alter_column(table, "reserved_until", nullable=True)
    op.create_check_constraint(
        "ck_allocation_exactly_one_source", table,
        "(application_vehicle_id IS NULL) <> (fast_deal_vehicle_id IS NULL)",
    )
    op.create_check_constraint(
        "ck_allocation_reserved_until_required", table,
        "reserved_until IS NOT NULL OR fast_deal_vehicle_id IS NOT NULL",
    )
    op.create_index(
        "idx_allocation_fast_deal_vehicle", table, ["fast_deal_vehicle_id"],
        postgresql_where=sa.text("fast_deal_vehicle_id IS NOT NULL"),
    )


def _extend_applied_supports() -> None:
    table = "application_applied_supports"
    op.add_column(table, sa.Column("fast_deal_id", UUID(as_uuid=True), nullable=True))
    op.add_column(table, sa.Column("fast_deal_vehicle_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_applied_supports_fast_deal", table, "fast_deals",
        ["fast_deal_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_applied_supports_fast_deal_vehicle", table, "fast_deal_vehicles",
        ["fast_deal_vehicle_id"], ["id"], ondelete="RESTRICT",
    )
    op.drop_constraint("ck_application_applied_supports_exactly_one_source", table, type_="check")
    op.create_check_constraint(
        "ck_application_applied_supports_exactly_one_source", table,
        "num_nonnulls(application_id, exchange_request_id, fast_deal_id) = 1",
    )
    op.create_check_constraint(
        "ck_application_applied_supports_fast_deal_position", table,
        "fast_deal_vehicle_id IS NULL OR fast_deal_id IS NOT NULL",
    )
    op.create_index(
        "idx_application_applied_supports_fast_deal", table, ["fast_deal_id"],
        postgresql_where=sa.text("fast_deal_id IS NOT NULL"),
    )
    op.create_index(
        "uq_application_applied_supports_fast_deal_position_program", table,
        ["fast_deal_vehicle_id", "support_program_id"], unique=True,
        postgresql_where=sa.text("fast_deal_vehicle_id IS NOT NULL"),
    )


def _extend_compensations() -> None:
    table = "compensations"
    op.add_column(table, sa.Column("fast_deal_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_compensations_fast_deal", table, "fast_deals",
        ["fast_deal_id"], ["id"], ondelete="RESTRICT",
    )
    op.drop_constraint("ck_compensations_source", table, type_="check")
    op.drop_constraint("ck_compensations_exchange_source_link", table, type_="check")
    op.create_check_constraint(
        "ck_compensations_source", table, "source IN ('platform', 'exchange', 'fast_deal')"
    )
    op.create_check_constraint(
        "ck_compensations_exchange_source_link", table,
        "(source = 'platform' AND application_id IS NOT NULL "
        "AND exchange_request_id IS NULL AND fast_deal_id IS NULL) OR "
        "(source = 'exchange' AND exchange_request_id IS NOT NULL "
        "AND application_id IS NULL AND fast_deal_id IS NULL) OR "
        "(source = 'fast_deal' AND fast_deal_id IS NOT NULL "
        "AND application_id IS NULL AND exchange_request_id IS NULL)",
    )
    op.create_index(
        "idx_compensations_fast_deal_id", table, ["fast_deal_id"],
        postgresql_where=sa.text("fast_deal_id IS NOT NULL"),
    )


_OLD_SOURCES = "'platform','dealer_account','exchange','dealer_site','distributor_site'"
_NEW_SOURCES = _OLD_SOURCES + ",'dealer_to_leasing','leasing_to_dealer'"
_OLD_ORIGIN = (
    "(exchange_request_id IS NOT NULL AND application_id IS NULL "
    "AND leasing_company_application_id IS NULL AND source_type = 'exchange') "
    "OR (exchange_request_id IS NULL AND application_id IS NOT NULL "
    "AND leasing_company_application_id IS NOT NULL "
    "AND source_type IN ('platform','dealer_account','dealer_site','distributor_site'))"
)
_NEW_ORIGIN = (
    "(exchange_request_id IS NOT NULL AND application_id IS NULL "
    "AND leasing_company_application_id IS NULL AND fast_deal_id IS NULL "
    "AND source_type = 'exchange') "
    "OR (exchange_request_id IS NULL AND application_id IS NOT NULL "
    "AND leasing_company_application_id IS NOT NULL AND fast_deal_id IS NULL "
    "AND source_type IN ('platform','dealer_account','dealer_site','distributor_site')) "
    "OR (exchange_request_id IS NULL AND application_id IS NULL "
    "AND leasing_company_application_id IS NULL AND fast_deal_id IS NOT NULL "
    "AND source_type IN ('dealer_to_leasing','leasing_to_dealer'))"
)


def _extend_monetization() -> None:
    op.add_column("monetization_deals", sa.Column("fast_deal_id", UUID(as_uuid=True), nullable=True))
    op.drop_constraint("ck_monetization_source_type", "monetization_program_sources", type_="check")
    op.create_check_constraint(
        "ck_monetization_source_type", "monetization_program_sources",
        f"source_type IN ({_NEW_SOURCES})",
    )
    op.drop_constraint("ck_monetization_deal_origin", "monetization_deals", type_="check")
    op.create_check_constraint("ck_monetization_deal_origin", "monetization_deals", _NEW_ORIGIN)
    op.create_unique_constraint(
        "uq_monetization_deal_fast_deal", "monetization_deals", ["fast_deal_id"]
    )


def _relax_claimed_price() -> None:
    """Request-priced units may be claimed on the strength of an allocation price."""
    table = "special_equipment_products"
    op.drop_constraint("ck_special_equipment_products_claimed_price", table, type_="check")
    op.create_check_constraint(
        "ck_special_equipment_products_claimed_price", table,
        "sale_status NOT IN ('reserved', 'sold') OR price_on_request OR price IS NOT NULL",
    )
    op.execute(
        """
        CREATE FUNCTION se_product_claimed_price_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.sale_status IN ('reserved', 'sold')
             AND NEW.price_on_request
             AND (NEW.price_from IS NULL OR NEW.price_from <= 0)
             AND NOT EXISTS (
               SELECT 1 FROM application_vehicle_allocations a
               WHERE a.product_id = NEW.id AND a.released_at IS NULL AND a.unit_price > 0
             ) THEN
            RAISE EXCEPTION
              'a request-priced product can be claimed only with an agreed allocation price'
              USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_special_equipment_products_claimed_price';
          END IF;
          RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_se_product_claimed_price_guard "
        "BEFORE INSERT OR UPDATE OF sale_status, price_on_request, price_from "
        "ON special_equipment_products "
        "FOR EACH ROW EXECUTE FUNCTION se_product_claimed_price_guard()"
    )


def _scalar(sql: str) -> bool:
    return bool(op.get_bind().execute(sa.text(sql)).scalar())


def downgrade() -> None:
    # Dropping the new source would silently erase history and financial snapshots.
    if _scalar("SELECT EXISTS (SELECT 1 FROM fast_deals)"):
        raise RuntimeError("Cannot downgrade: fast deals exist; their history would be lost")
    if _scalar(
        "SELECT EXISTS (SELECT 1 FROM monetization_deals WHERE fast_deal_id IS NOT NULL) "
        "OR EXISTS (SELECT 1 FROM monetization_program_sources "
        "WHERE source_type IN ('dealer_to_leasing', 'leasing_to_dealer'))"
    ):
        raise RuntimeError("Cannot downgrade: monetization data uses fast deal sources")
    if _scalar(
        "SELECT EXISTS (SELECT 1 FROM special_equipment_products "
        "WHERE sale_status IN ('reserved', 'sold') AND price_on_request "
        "AND (price_from IS NULL OR price_from <= 0))"
    ):
        raise RuntimeError(
            "Cannot downgrade: claimed request-priced products rely on allocation prices"
        )

    table = "special_equipment_products"
    op.execute("DROP TRIGGER trg_se_product_claimed_price_guard ON special_equipment_products")
    op.execute("DROP FUNCTION se_product_claimed_price_guard()")
    op.drop_constraint("ck_special_equipment_products_claimed_price", table, type_="check")
    op.create_check_constraint(
        "ck_special_equipment_products_claimed_price", table,
        "sale_status NOT IN ('reserved', 'sold') OR "
        "(price_on_request AND price_from > 0) OR "
        "(NOT price_on_request AND price IS NOT NULL)",
    )

    op.drop_constraint("uq_monetization_deal_fast_deal", "monetization_deals", type_="unique")
    op.drop_constraint("ck_monetization_deal_origin", "monetization_deals", type_="check")
    op.create_check_constraint("ck_monetization_deal_origin", "monetization_deals", _OLD_ORIGIN)
    op.drop_constraint("ck_monetization_source_type", "monetization_program_sources", type_="check")
    op.create_check_constraint(
        "ck_monetization_source_type", "monetization_program_sources",
        f"source_type IN ({_OLD_SOURCES})",
    )
    op.drop_column("monetization_deals", "fast_deal_id")

    op.drop_index("idx_compensations_fast_deal_id", table_name="compensations")
    op.drop_constraint("ck_compensations_exchange_source_link", "compensations", type_="check")
    op.drop_constraint("ck_compensations_source", "compensations", type_="check")
    op.create_check_constraint(
        "ck_compensations_source", "compensations", "source IN ('platform', 'exchange')"
    )
    op.create_check_constraint(
        "ck_compensations_exchange_source_link", "compensations",
        "(source = 'platform' AND application_id IS NOT NULL "
        "AND exchange_request_id IS NULL) OR "
        "(source = 'exchange' AND exchange_request_id IS NOT NULL "
        "AND application_id IS NULL)",
    )
    op.drop_constraint("fk_compensations_fast_deal", "compensations", type_="foreignkey")
    op.drop_column("compensations", "fast_deal_id")

    supports = "application_applied_supports"
    op.drop_index("uq_application_applied_supports_fast_deal_position_program", table_name=supports)
    op.drop_index("idx_application_applied_supports_fast_deal", table_name=supports)
    op.drop_constraint("ck_application_applied_supports_fast_deal_position", supports, type_="check")
    op.drop_constraint("ck_application_applied_supports_exactly_one_source", supports, type_="check")
    op.create_check_constraint(
        "ck_application_applied_supports_exactly_one_source", supports,
        "(application_id IS NULL) <> (exchange_request_id IS NULL)",
    )
    op.drop_constraint("fk_applied_supports_fast_deal_vehicle", supports, type_="foreignkey")
    op.drop_constraint("fk_applied_supports_fast_deal", supports, type_="foreignkey")
    op.drop_column(supports, "fast_deal_vehicle_id")
    op.drop_column(supports, "fast_deal_id")

    allocations = "application_vehicle_allocations"
    op.drop_index("idx_allocation_fast_deal_vehicle", table_name=allocations)
    op.drop_constraint("ck_allocation_reserved_until_required", allocations, type_="check")
    op.drop_constraint("ck_allocation_exactly_one_source", allocations, type_="check")
    op.alter_column(allocations, "reserved_until", nullable=False)
    op.alter_column(allocations, "application_vehicle_id", nullable=False)
    op.drop_constraint("fk_allocation_fast_deal_vehicle", allocations, type_="foreignkey")
    op.drop_column(allocations, "fast_deal_vehicle_id")

    op.execute("DROP TRIGGER trg_fast_deal_offers_immutable ON fast_deal_offers")
    op.execute("DROP FUNCTION fast_deal_offers_immutable()")
    op.drop_constraint("fk_fast_deal_lc_applications_current_offer",
                       "fast_deal_lc_applications", type_="foreignkey")
    op.drop_constraint("fk_fast_deals_final_offer", "fast_deals", type_="foreignkey")
    for name in (
        "fast_deal_assignees",
        "fast_deal_support_requests",
        "fast_deal_status_history",
        "fast_deal_offers",
        "fast_deal_files",
        "fast_deal_lc_applications",
        "fast_deal_vehicles",
        "fast_deals",
    ):
        op.drop_table(name)

"""Reliable notification events, inbox deduplication and email delivery.

Revision ID: 111
Revises: 110
Create Date: 2026-09-07
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "111"
down_revision: str | None = "110"
branch_labels: str | None = None
depends_on: str | None = None

_NEW_TYPES = (
    "exchange_request_changed", "exchange_bid_withdrawn", "exchange_deadline",
    "exchange_request_finalized", "exchange_bid_not_selected",
)
_OLD_TYPES = (
    "application_status", "document_request", "approval", "general",
    "document_status", "leasing_approval", "system", "exchange_new_request",
    "exchange_new_bid", "exchange_bid_updated", "exchange_bid_accepted",
)
_LOGGER = logging.getLogger("carcraft-backend")


def _log_unresolved_owners(table: str, owner_column: str) -> None:
    """Report only internal record UUIDs, never names, email or phone."""
    connection = op.get_bind()
    count = connection.scalar(sa.text(f"SELECT count(*) FROM {table} WHERE {owner_column} IS NULL"))
    if not count:
        return
    _LOGGER.warning(
        "notification_owner_backfill_unresolved",
        extra={"migration": "111", "table": table, "unresolved_count": count},
    )
    # Stream bounded batches so a large legacy installation does not load all IDs.
    records = connection.execute(
        sa.text(f"SELECT id FROM {table} WHERE {owner_column} IS NULL ORDER BY id")
    )
    while rows := records.fetchmany(100):
        _LOGGER.warning(
            "notification_owner_backfill_unresolved_records",
            extra={"migration": "111", "table": table, "record_ids": [str(row.id) for row in rows]},
        )


def _backfill_owners() -> None:
    op.execute("""
        WITH membership AS (
            SELECT id AS user_id, company_id FROM users WHERE company_id IS NOT NULL
            UNION SELECT user_id, company_id FROM user_companies
            UNION
            SELECT lcu.user_id, lc.company_id
            FROM leasing_company_users lcu
            JOIN leasing_companies lc ON lc.id = lcu.leasing_company_id
            WHERE lc.company_id IS NOT NULL
        ), proven AS (
            SELECT m.user_id, (array_agg(DISTINCT m.company_id))[1] AS company_id
            FROM membership m JOIN companies c ON c.id = m.company_id
            WHERE c.company_type = 'leasing_company'
            GROUP BY m.user_id HAVING count(DISTINCT m.company_id) = 1
        )
        UPDATE exchange_requests r SET lc_company_id = p.company_id
        FROM proven p WHERE p.user_id = r.lc_user_id
    """)
    op.execute("""
        WITH membership AS (
            SELECT id AS user_id, company_id FROM users WHERE company_id IS NOT NULL
            UNION SELECT user_id, company_id FROM user_companies
        ), proven AS (
            SELECT m.user_id, (array_agg(DISTINCT m.company_id))[1] AS company_id
            FROM membership m JOIN companies c ON c.id = m.company_id
            WHERE c.company_type = 'dealer'
            GROUP BY m.user_id HAVING count(DISTINCT m.company_id) = 1
        )
        UPDATE exchange_bids b SET dealer_company_id = p.company_id
        FROM proven p WHERE p.user_id = b.dealer_id
    """)
    _log_unresolved_owners("exchange_requests", "lc_company_id")
    _log_unresolved_owners("exchange_bids", "dealer_company_id")


def upgrade() -> None:
    for value in _NEW_TYPES:
        op.execute(f"ALTER TYPE notification_type ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column("notifications", sa.Column("event_id", pg.UUID(as_uuid=True), nullable=True))
    op.add_column("notifications", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("uq_notifications_event_user", "notifications", ["event_id", "user_id"], unique=True,
                    postgresql_where=sa.text("event_id IS NOT NULL"))
    op.add_column("email_preferences", sa.Column("exchange_emails", sa.Boolean(), server_default=sa.true(), nullable=False))

    op.create_table(
        "notification_event_outbox",
        sa.Column("event_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("sequence", sa.BigInteger(), sa.Identity(), nullable=False, unique=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("occurrence_key", sa.String(500), nullable=True, unique=True),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_publish_error", sa.String(250), nullable=True),
    )
    op.create_index("ix_notification_outbox_due", "notification_event_outbox", ["next_attempt_at"],
                    postgresql_where=sa.text("published_at IS NULL"))
    op.create_index("ix_notification_outbox_aggregate", "notification_event_outbox", ["aggregate_id", "sequence"])
    op.create_table(
        "notification_event_receipts",
        sa.Column("event_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "notification_email_batches",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("delivery_mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_token", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_id", sa.String(255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notification_batches_due", "notification_email_batches", ["status", "next_attempt_at"])
    op.create_table(
        "notification_email_deliveries",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("notification_id", pg.UUID(as_uuid=True), sa.ForeignKey("notifications.id"), nullable=False),
        sa.Column("event_id", pg.UUID(as_uuid=True), sa.ForeignKey("notification_event_receipts.event_id"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipient_role", sa.String(32), nullable=False),
        sa.Column("recipient_company_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("batch_id", pg.UUID(as_uuid=True), sa.ForeignKey("notification_email_batches.id"), nullable=True),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("delivery_mode", sa.String(16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(250), nullable=True),
        sa.Column("message_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("event_id", "user_id", name="uq_notification_delivery_event_user"),
    )
    op.create_index("ix_notification_deliveries_due", "notification_email_deliveries", ["status", "next_attempt_at"])
    op.create_index("ix_notification_deliveries_batch", "notification_email_deliveries", ["batch_id"])

    for table in ("exchange_requests", "exchange_cart_items"):
        op.alter_column(table, "expiration_date", new_column_name="expiration_at", type_=sa.DateTime(timezone=True),
                        existing_type=sa.Date(), existing_nullable=True,
                        postgresql_using="(expiration_date + time '23:59:59') AT TIME ZONE 'Europe/Moscow'")
    op.add_column("exchange_requests", sa.Column("lc_company_id", pg.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_exchange_requests_lc_company_id", "exchange_requests", "companies", ["lc_company_id"], ["id"], ondelete="SET NULL")
    op.add_column("exchange_bids", sa.Column("dealer_company_id", pg.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_exchange_bids_dealer_company_id", "exchange_bids", "companies", ["dealer_company_id"], ["id"], ondelete="SET NULL")
    op.create_index("idx_exchange_requests_lc_company", "exchange_requests", ["lc_company_id"])
    op.create_index("idx_exchange_requests_expiration", "exchange_requests", ["expiration_at"])
    _backfill_owners()
    op.create_index("idx_application_vehicles_reservation_due", "application_vehicles", ["reserve_expires_at", "id"],
                    postgresql_where=sa.text("car_status = 'confirmed' AND reserve_expires_at IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("idx_application_vehicles_reservation_due", table_name="application_vehicles")
    op.drop_index("idx_exchange_requests_expiration", table_name="exchange_requests")
    op.drop_index("idx_exchange_requests_lc_company", table_name="exchange_requests")
    op.drop_constraint("fk_exchange_bids_dealer_company_id", "exchange_bids", type_="foreignkey")
    op.drop_column("exchange_bids", "dealer_company_id")
    op.drop_constraint("fk_exchange_requests_lc_company_id", "exchange_requests", type_="foreignkey")
    op.drop_column("exchange_requests", "lc_company_id")
    for table in ("exchange_requests", "exchange_cart_items"):
        op.alter_column(table, "expiration_at", new_column_name="expiration_date", type_=sa.Date(),
                        existing_type=sa.DateTime(timezone=True), existing_nullable=True,
                        postgresql_using="(expiration_at AT TIME ZONE 'Europe/Moscow')::date")

    op.drop_table("notification_email_deliveries")
    op.drop_table("notification_email_batches")
    op.drop_table("notification_event_receipts")
    op.drop_table("notification_event_outbox")
    op.drop_column("email_preferences", "exchange_emails")
    op.drop_index("uq_notifications_event_user", table_name="notifications")
    op.drop_column("notifications", "deleted_at")
    op.drop_column("notifications", "event_id")

    # Keep inbox history readable by the old application; do not delete rows.
    values = ", ".join(f"'{value}'" for value in _NEW_TYPES)
    op.execute(f"UPDATE notifications SET type = 'system' WHERE type::text IN ({values})")
    op.execute("ALTER TABLE notifications ALTER COLUMN type TYPE text USING type::text")
    op.execute("DROP TYPE notification_type")
    old_values = ", ".join(f"'{value}'" for value in _OLD_TYPES)
    op.execute(f"CREATE TYPE notification_type AS ENUM ({old_values})")
    op.execute("ALTER TABLE notifications ALTER COLUMN type TYPE notification_type USING type::notification_type")

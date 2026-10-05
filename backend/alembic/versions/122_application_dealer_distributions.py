"""Persist idempotent dealer quantity distributions without splitting order lines."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "122"
down_revision = "121"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_dealer_distribution_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "distributor_company_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("client_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["application_id"], ["leasing_applications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["distributor_company_id"], ["companies.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "application_id",
            "distributor_company_id",
            "client_request_id",
            name="uq_dealer_distribution_request",
        ),
    )
    op.create_table(
        "application_vehicle_dealer_distributions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "application_vehicle_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("dealer_company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["application_vehicle_id"], ["application_vehicles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["dealer_company_id"], ["companies.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["application_dealer_distribution_requests.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("quantity > 0", name="ck_dealer_distribution_quantity"),
        sa.UniqueConstraint(
            "request_id",
            "application_vehicle_id",
            name="uq_dealer_distribution_request_line",
        ),
    )
    op.create_index(
        "idx_dealer_distribution_line",
        "application_vehicle_dealer_distributions",
        ["application_vehicle_id"],
    )
    op.create_index(
        "idx_dealer_distribution_dealer",
        "application_vehicle_dealer_distributions",
        ["dealer_company_id"],
    )


def downgrade() -> None:
    op.drop_table("application_vehicle_dealer_distributions")
    op.drop_table("application_dealer_distribution_requests")

"""Add additional equipment and services catalogs.

Revision ID: 060
Revises: 059
Create Date: 2026-06-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "060"
down_revision: str | None = "059"
branch_labels: str | None = None
depends_on: str | None = None


EQUIPMENTS = [
    ("tire_set", "Комплект шин"),
    ("tire_service", "Шиномонтаж"),
    ("tire_storage", "Хранение шин"),
    ("telematics", "Установка телематики"),
    ("mats", "Коврики"),
    ("alarm", "Сигнализация"),
    ("partial_wrapping", "Оклейка частичная"),
    ("full_wrapping", "Оклейка полная"),
    ("protective_coating", "Нанесение защитного покрытия"),
    ("service_contract", "Сервисный контракт"),
    ("crankcase", "Защита картера"),
    ("mudflaps", "Брызговики"),
    ("tinting", "Тонировка стекол"),
]

SERVICES = [
    ("osago", "Страхование ОСАГО"),
    ("kasko", "Страхование КАСКО"),
    ("dsago", "Страхование ДСАГО"),
    ("gap_insurance", "GAP-страхование"),
    ("road_help", "Помощь на дороге"),
    ("legal_support", "Юридическое сопровождение"),
    ("fuel_cards", "Топливные карты"),
    ("gibdd_registration", "Постановка на учет в ГИБДД"),
    ("extended_warranty", "Расширенная гарантия"),
    ("delivery", "Доставка"),
]


def upgrade() -> None:
    op.create_table(
        "additional_equipments",
        sa.Column("equipment_code", sa.String(length=64), nullable=False),
        sa.Column("equipment_display_name", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("equipment_code"),
    )
    op.create_table(
        "additional_services",
        sa.Column("service_code", sa.String(length=64), nullable=False),
        sa.Column("service_display_name", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("service_code"),
    )
    op.add_column(
        "shopping_cart",
        sa.Column(
            "equipments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "shopping_cart",
        sa.Column(
            "services",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "application_vehicles",
        sa.Column(
            "equipments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "application_vehicles",
        sa.Column(
            "services",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.bulk_insert(
        sa.table(
            "additional_equipments",
            sa.column("equipment_code", sa.String),
            sa.column("equipment_display_name", sa.String),
            sa.column("sort_order", sa.Integer),
        ),
        [
            {
                "equipment_code": code,
                "equipment_display_name": name,
                "sort_order": index,
            }
            for index, (code, name) in enumerate(EQUIPMENTS, start=1)
        ],
    )
    op.bulk_insert(
        sa.table(
            "additional_services",
            sa.column("service_code", sa.String),
            sa.column("service_display_name", sa.String),
            sa.column("sort_order", sa.Integer),
        ),
        [
            {
                "service_code": code,
                "service_display_name": name,
                "sort_order": index,
            }
            for index, (code, name) in enumerate(SERVICES, start=1)
        ],
    )


def downgrade() -> None:
    op.drop_column("application_vehicles", "services")
    op.drop_column("application_vehicles", "equipments")
    op.drop_column("shopping_cart", "services")
    op.drop_column("shopping_cart", "equipments")
    op.drop_table("additional_services")
    op.drop_table("additional_equipments")

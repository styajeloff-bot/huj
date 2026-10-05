"""SQLAlchemy ORM models for cities, warehouses, and warehouse transfers.

Legacy Vehicle, FeaturedVehicle, and VehicleWarehouse retired in task refactor/retire-legacy-catalog.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, synonym

from infrastructure.models import Base


class City(Base):
    """A city used as warehouse location reference."""

    __tablename__ = "cities"
    __table_args__ = (
        sa.Index("idx_cities_name", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()
    )


class Warehouse(Base):
    """Physical warehouse/storage location owned by a dealer or distributor."""

    __tablename__ = "warehouses"
    __table_args__ = (
        sa.CheckConstraint(
            "owner_company_type IN ('dealer', 'distributor')",
            name="ck_warehouses_owner_company_type",
        ),
        sa.Index("idx_warehouses_name", "name"),
        sa.Index("idx_warehouses_address", "address"),
        sa.Index("idx_warehouses_owner_company_id", "owner_company_id"),
        sa.Index("idx_warehouses_owner_company_type", "owner_company_type"),
        sa.Index("idx_warehouses_city_id", "city_id"),
        sa.Index("idx_warehouses_category_id", "category_id"),
        sa.Index("idx_warehouses_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    owner_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT", name="fk_warehouses_owner_company_id_companies"),
        nullable=False,
    )
    owner_company_type: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    city_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("cities.id", ondelete="SET NULL"),
        nullable=True,
    )
    address: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_categories.id", ondelete="RESTRICT",
            name="fk_warehouses_category_id_special_equipment_categories",
        ),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True, server_default=sa.func.current_timestamp()
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True, server_default=sa.func.current_timestamp()
    )

    company_id: Mapped[uuid.UUID] = synonym("owner_company_id")
    dealer_id: Mapped[uuid.UUID] = synonym("owner_company_id")

    @hybrid_property
    def status(self) -> str:
        return "active" if self.is_active else "inactive"

    @status.inplace.expression
    @classmethod
    def _status_expression(cls) -> Any:
        return sa.case(
            (cls.is_active.is_(True), "active"),
            else_="inactive",
        )

    @hybrid_property
    def brand(self) -> str | None:
        return None

    @brand.inplace.expression
    @classmethod
    def _brand_expression(cls) -> Any:
        from infrastructure.models.special_equipment import SpecialEquipmentMark

        return (
            sa.select(sa.func.string_agg(
                SpecialEquipmentMark.name,
                aggregate_order_by(sa.literal(", "), SpecialEquipmentMark.name.asc(), SpecialEquipmentMark.id.asc()),
            ))
            .select_from(WarehouseMark)
            .join(SpecialEquipmentMark, SpecialEquipmentMark.id == WarehouseMark.mark_id)
            .where(WarehouseMark.warehouse_id == cls.id)
            .correlate(cls)
            .scalar_subquery()
        )


class WarehouseMark(Base):
    """Marks explicitly selected in a warehouse's settings."""

    __tablename__ = "warehouse_marks"
    __table_args__ = (sa.Index("idx_warehouse_marks_mark_id", "mark_id"),)

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("warehouses.id", ondelete="CASCADE", name="fk_warehouse_marks_warehouse_id"),
        primary_key=True,
    )
    mark_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_marks.id", ondelete="RESTRICT", name="fk_warehouse_marks_mark_id"),
        primary_key=True,
    )


class WarehouseAccessRule(Base):
    """Rule determining participant access and permissions to a warehouse."""

    __tablename__ = "warehouse_access_rules"
    __table_args__ = (
        sa.CheckConstraint(
            "target_type IN ('dealer', 'distributor')",
            name="ck_warehouse_access_rules_target_type",
        ),
        sa.CheckConstraint(
            "warehouse_access_type IN ('A', 'B', 'C')",
            name="ck_warehouse_access_rules_access_type",
        ),
        sa.Index(
            "idx_warehouse_access_rules_unique_rule",
            "warehouse_id",
            "target_type",
            "target_id",
            sa.text("COALESCE(site_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            sa.text("COALESCE(brand_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            unique=True,
        ),
        sa.Index("idx_warehouse_access_rules_target", "target_id", "is_active"),
        sa.Index("idx_warehouse_access_rules_warehouse", "warehouse_id", "is_active"),
        sa.Index("idx_warehouse_access_rules_source_group", "source_group_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("warehouses.id", ondelete="CASCADE", name="fk_warehouse_access_rules_warehouse_id"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="CASCADE", name="fk_warehouse_access_rules_target_id"),
        nullable=False,
    )
    warehouse_access_type: Mapped[str] = mapped_column(sa.String(5), nullable=False)
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("catalog_storefronts.id", ondelete="SET NULL", name="fk_warehouse_access_rules_site_id"),
        nullable=True,
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_marks.id", ondelete="SET NULL", name="fk_warehouse_access_rules_brand_id"),
        nullable=True,
    )
    source_group_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("dealer_groups.id", ondelete="SET NULL", name="fk_warehouse_access_rules_source_group_id"),
        nullable=True,
    )
    is_visible: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    can_create_application: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    )



class VehicleWarehouseTransfer(Base):
    """Append-only audit history for completed warehouse vehicle transfers."""

    __tablename__ = "vehicle_warehouse_transfers"
    __table_args__ = (
        sa.CheckConstraint(
            "source_warehouse_id IS NULL OR destination_warehouse_id IS NULL OR source_warehouse_id <> destination_warehouse_id",
            name="ck_vehicle_warehouse_transfers_distinct_warehouses",
        ),
        sa.Index(
            "idx_vehicle_warehouse_transfers_product_created_at",
            "product_id",
            sa.desc("created_at"),
        ),
        sa.Index(
            "idx_vehicle_warehouse_transfers_source_created_at",
            "source_warehouse_id",
            sa.desc("created_at"),
        ),
        sa.Index(
            "idx_vehicle_warehouse_transfers_destination_created_at",
            "destination_warehouse_id",
            sa.desc("created_at"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_products.id", ondelete="SET NULL"),
        nullable=True,
    )
    vehicle_id = synonym("product_id")
    source_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("warehouses.id", ondelete="SET NULL"),
        nullable=True,
    )
    destination_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("warehouses.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    source_warehouse_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    destination_warehouse_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    )

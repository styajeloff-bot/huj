"""SQLAlchemy models for the corrected special-equipment catalog."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, MappedColumn, mapped_column, synonym

from infrastructure.models import Base


def _uuid_pk() -> MappedColumn[uuid.UUID]:
    return mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )


class _DirectoryFields:
    """Shared immutable-code directory fields."""

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    slug: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    lock_version: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, default=1, server_default=sa.text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class SpecialEquipmentCategory(_DirectoryFields, Base):
    """A reusable node in the category DAG."""

    __tablename__ = "special_equipment_categories"
    __table_args__ = (
        sa.UniqueConstraint("code", name="uq_special_equipment_categories_code"),
        sa.UniqueConstraint("slug", name="uq_special_equipment_categories_slug"),
        sa.CheckConstraint(
            "usage_metric IN ('mileage_km', 'engine_hours')",
            name="ck_special_equipment_categories_usage_metric",
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_special_equipment_categories_sort_order_nonnegative",
        ),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_special_equipment_categories_lock_version",
        ),
        sa.Index(
            "idx_special_equipment_categories_active_sort",
            "is_active",
            "sort_order",
            "id",
        ),
        sa.Index(
            "idx_se_categories_updated_desc",
            sa.text("GREATEST(created_at, updated_at) DESC"),
            sa.text("id DESC"),
        ),
        sa.Index(
            "idx_se_categories_attachment",
            "id",
            postgresql_where=sa.text("is_attachment_category"),
        ),
        sa.Index("idx_se_categories_visible", "is_visible_in_catalog"),
    )

    usage_metric: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    is_attachment_category: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        server_default=sa.false(),
    )
    is_visible_in_catalog: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=True,
        server_default=sa.true(),
    )
    image_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )


class SpecialEquipmentCategoryRelation(Base):
    """One directed parent → child edge in the category DAG."""

    __tablename__ = "special_equipment_category_relations"
    __table_args__ = (
        sa.CheckConstraint(
            "parent_id <> child_id",
            name="ck_special_equipment_category_relations_not_self",
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_special_equipment_category_relations_sort_order",
        ),
        sa.Index(
            "idx_special_equipment_category_relations_child_parent",
            "child_id",
            "parent_id",
        ),
    )

    parent_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_categories.id",
            name="fk_special_equipment_category_relations_parent",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_categories.id",
            name="fk_special_equipment_category_relations_child",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    sort_order: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )


class SpecialEquipmentMark(_DirectoryFields, Base):
    __tablename__ = "special_equipment_marks"
    __table_args__ = (
        sa.UniqueConstraint("code", name="uq_special_equipment_marks_code"),
        sa.UniqueConstraint("slug", name="uq_special_equipment_marks_slug"),
        sa.UniqueConstraint("name", name="uq_special_equipment_marks_name"),
        sa.CheckConstraint(
            "lock_version >= 1", name="ck_special_equipment_marks_lock_version"
        ),
        sa.Index(
            "idx_se_marks_name_search",
            sa.func.lower(sa.column("name")).label("name_search"),
            postgresql_using="gin",
            postgresql_ops={"name_search": "gin_trgm_ops"},
        ),
    )


class SpecialEquipmentModel(_DirectoryFields, Base):
    __tablename__ = "special_equipment_models"
    __table_args__ = (
        sa.UniqueConstraint("code", name="uq_special_equipment_models_code"),
        sa.UniqueConstraint(
            "mark_id", "slug", name="uq_special_equipment_models_mark_slug"
        ),
        sa.UniqueConstraint(
            "mark_id", "name", name="uq_special_equipment_models_mark_name"
        ),
        sa.CheckConstraint(
            "lock_version >= 1", name="ck_special_equipment_models_lock_version"
        ),
        sa.Index("idx_special_equipment_models_mark", "mark_id", "name", "id"),
        sa.Index("idx_special_equipment_models_category", "category_id"),
        sa.Index(
            "idx_se_models_name_search",
            sa.func.lower(sa.column("name")).label("name_search"),
            postgresql_using="gin",
            postgresql_ops={"name_search": "gin_trgm_ops"},
        ),
    )

    mark_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_marks.id",
            name="fk_special_equipment_models_mark",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_categories.id",
            name="fk_special_equipment_models_category",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=True,
    )


class SpecialEquipmentModification(_DirectoryFields, Base):
    __tablename__ = "special_equipment_modifications"
    __table_args__ = (
        sa.UniqueConstraint(
            "code", name="uq_special_equipment_modifications_code"
        ),
        sa.UniqueConstraint(
            "model_id",
            "slug",
            name="uq_special_equipment_modifications_model_slug",
        ),
        sa.UniqueConstraint(
            "model_id",
            "name",
            name="uq_special_equipment_modifications_model_name",
        ),
        sa.UniqueConstraint(
            "id",
            "model_id",
            name="uq_special_equipment_modifications_id_model",
        ),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_special_equipment_modifications_lock_version",
        ),
        sa.CheckConstraint(
            "year_from IS NULL OR year_from BETWEEN 1900 AND 2200",
            name="ck_special_equipment_modifications_year_from",
        ),
        sa.CheckConstraint(
            "year_to IS NULL OR year_to BETWEEN 1900 AND 2200",
            name="ck_special_equipment_modifications_year_to",
        ),
        sa.CheckConstraint(
            "year_from IS NULL OR year_to IS NULL OR year_from <= year_to",
            name="ck_special_equipment_modifications_year_range",
        ),
        sa.Index(
            "idx_special_equipment_modifications_model", "model_id", "name", "id"
        ),
        sa.Index(
            "idx_se_modifications_name_search",
            sa.func.lower(sa.column("name")).label("name_search"),
            postgresql_using="gin",
            postgresql_ops={"name_search": "gin_trgm_ops"},
        ),
    )

    model_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_models.id",
            name="fk_special_equipment_modifications_model",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    year_from: Mapped[int | None] = mapped_column(sa.SmallInteger, nullable=True)
    year_to: Mapped[int | None] = mapped_column(sa.SmallInteger, nullable=True)

    @property
    def complectation_id(self) -> str:
        return str(self.id)

    @property
    def group_name(self) -> str:
        return self.name


class SpecialEquipmentTrim(_DirectoryFields, Base):
    """One configuration/trim owned by a concrete modification."""

    __tablename__ = "special_equipment_trims"
    __table_args__ = (
        sa.UniqueConstraint(
            "id",
            "modification_id",
            name="uq_se_trims_id_modification",
        ),
        sa.CheckConstraint("sort_order >= 0", name="ck_se_trims_sort_order"),
        sa.CheckConstraint("lock_version >= 1", name="ck_se_trims_lock_version"),
        sa.Index(
            "uq_se_trims_modification_code_normalized",
            "modification_id",
            sa.text("lower(btrim(code))"),
            unique=True,
        ),
        sa.Index(
            "uq_se_trims_modification_name_normalized",
            "modification_id",
            sa.text("lower(btrim(name))"),
            unique=True,
        ),
        sa.Index(
            "uq_se_trims_modification_slug_normalized",
            "modification_id",
            sa.text("lower(btrim(slug))"),
            unique=True,
        ),
        sa.Index(
            "idx_se_trims_modification_active_sort",
            "modification_id",
            "is_active",
            "sort_order",
            "name",
            "id",
        ),
    )

    modification_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_modifications.id",
            name="fk_se_trims_modification",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )


class SpecialEquipmentTrimAttribute(Base):
    """One attribute assignment for a trim."""

    __tablename__ = "special_equipment_trim_attributes"
    __table_args__ = (
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_se_trim_attributes_sort_order",
        ),
    )

    trim_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_trims.id",
            name="fk_se_trim_attributes_trim",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_attributes.id",
            name="fk_se_trim_attributes_attribute",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_attribute_groups.id",
            name="fk_se_trim_attributes_group",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    is_required: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    is_filterable: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    sort_order: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )


class SpecialEquipmentTrimAttributeValue(Base):
    """One live typed characteristic value owned by a trim assignment."""

    __tablename__ = "special_equipment_trim_attribute_values"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["trim_id", "attribute_id"],
            [
                "special_equipment_trim_attributes.trim_id",
                "special_equipment_trim_attributes.attribute_id",
            ],
            name="fk_se_trim_attribute_values_assignment",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["attribute_id", "option_id"],
            [
                "special_equipment_attribute_options.attribute_id",
                "special_equipment_attribute_options.id",
            ],
            name="fk_se_trim_attribute_values_option_attribute",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        sa.CheckConstraint(
            "num_nonnulls(value_number, value_text, value_boolean, option_id) = 1",
            name="ck_se_trim_attribute_values_one_value",
        ),
        sa.CheckConstraint(
            "value_text IS NULL OR octet_length(value_text) <= 2000",
            name="ck_se_trim_attribute_values_text_size",
        ),
        sa.Index(
            "idx_se_trim_attribute_values_number",
            "attribute_id",
            "value_number",
            "trim_id",
            postgresql_where=sa.text("value_number IS NOT NULL"),
        ),
        sa.Index(
            "idx_se_trim_attribute_values_option",
            "attribute_id",
            "option_id",
            "trim_id",
            postgresql_where=sa.text("option_id IS NOT NULL"),
        ),
        sa.Index(
            "idx_se_trim_attribute_values_text_search",
            sa.func.lower(sa.column("value_text")).label("value_text_search"),
            postgresql_using="gin",
            postgresql_ops={"value_text_search": "gin_trgm_ops"},
            postgresql_where=sa.text("value_text IS NOT NULL"),
        ),
    )

    trim_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    attribute_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    option_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    value_number: Mapped[Decimal | None] = mapped_column(sa.Numeric(20, 4), nullable=True)
    value_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)


class SpecialEquipmentSuperstructure(_DirectoryFields, Base):
    """A superstructure type."""

    __tablename__ = "special_equipment_superstructures"
    __table_args__ = (
        sa.UniqueConstraint("code", name="uq_special_equipment_superstructures_code"),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_special_equipment_superstructures_lock_version",
        ),
        sa.Index(
            "uq_se_superstructures_code",
            sa.text("lower(btrim(code))"),
            unique=True,
        ),
        sa.Index(
            "uq_se_superstructures_name",
            sa.text("lower(btrim(name))"),
            unique=True,
        ),
        sa.Index(
            "uq_se_superstructures_slug",
            sa.text("lower(btrim(slug))"),
            unique=True,
        ),
        sa.Index(
            "idx_se_superstructures_active_name",
            "is_active",
            "name",
            "id",
        ),
    )


class SpecialEquipmentSuperstructureAttribute(Base):
    """An attribute assignment to a superstructure type under an attribute group."""

    __tablename__ = "special_equipment_superstructure_attributes"
    __table_args__ = (
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_se_superstructure_attributes_sort_order",
        ),
    )

    superstructure_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_superstructures.id", ondelete="CASCADE"),
        primary_key=True,
    )
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_attributes.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_attribute_groups.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_required: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    is_visible: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    is_filterable: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    sort_order: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )


class SpecialEquipmentSuperstructureCategory(Base):
    """M:N relationship between superstructure types and categories."""

    __tablename__ = "special_equipment_superstructure_categories"
    __table_args__ = (
        sa.Index(
            "idx_se_superstructure_categories_category",
            "category_id",
        ),
    )

    superstructure_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_superstructures.id",
            name="fk_se_superstructure_categories_superstructure",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_categories.id",
            name="fk_se_superstructure_categories_category",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("clock_timestamp()"),
    )


class SpecialEquipmentSuperstructureModelBackup152(Base):
    """Temporary backup table for migration 152 downgrade."""

    __tablename__ = "special_equipment_superstructures_model_backup_152"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    model_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    modification_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )


class SpecialEquipmentModificationCategory(Base):
    """Categories in which a modification is allowed to be advertised."""

    __tablename__ = "special_equipment_modification_categories"
    __table_args__ = (
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_se_modification_categories_sort_order",
        ),
        sa.UniqueConstraint(
            "modification_id",
            "sort_order",
            name="uq_se_modification_categories_order",
        ),
        sa.Index(
            "uq_se_modification_categories_primary",
            "modification_id",
            unique=True,
            postgresql_where=sa.text("is_primary"),
        ),
    )

    modification_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_modifications.id",
            name="fk_special_equipment_modification_categories_modification",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_categories.id",
            name="fk_special_equipment_modification_categories_category",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    sort_order: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    is_primary: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )


class SpecialEquipmentUnit(_DirectoryFields, Base):
    """A measurement unit for characteristics (mm, kg, hp, etc.)."""

    __tablename__ = "special_equipment_units"
    __table_args__ = (
        sa.UniqueConstraint("code", name="uq_special_equipment_units_code"),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_special_equipment_units_lock_version",
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 50",
            name="ck_special_equipment_units_name_len",
        ),
        sa.Index(
            "uq_se_units_lower_code",
            sa.text("lower(btrim(code))"),
            unique=True,
        ),
        sa.Index(
            "uq_se_units_lower_name",
            sa.text("lower(btrim(name))"),
            unique=True,
        ),
    )

    name: Mapped[str] = mapped_column(sa.String(50), nullable=False)


class SpecialEquipmentAttributeGroup(_DirectoryFields, Base):
    __tablename__ = "special_equipment_attribute_groups"
    __table_args__ = (
        sa.UniqueConstraint(
            "code", name="uq_special_equipment_attribute_groups_code"
        ),
        sa.UniqueConstraint(
            "slug", name="uq_special_equipment_attribute_groups_slug"
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_special_equipment_attribute_groups_sort_order",
        ),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_special_equipment_attribute_groups_lock_version",
        ),
    )

    sort_order: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )


class SpecialEquipmentAttribute(Base):
    __tablename__ = "special_equipment_attributes"
    __table_args__ = (
        sa.UniqueConstraint("code", name="uq_special_equipment_attributes_code"),
        sa.CheckConstraint(
            "data_type IN ('number', 'text', 'boolean', 'select')",
            name="ck_special_equipment_attributes_data_type",
        ),
        sa.CheckConstraint(
            "filter_kind IN ('exact', 'range', 'search')",
            name="ck_special_equipment_attributes_filter_kind",
        ),
        sa.CheckConstraint(
            "filter_kind <> 'range' OR data_type = 'number'",
            name="ck_special_equipment_attributes_range_number",
        ),
        sa.CheckConstraint(
            "filter_kind IS DISTINCT FROM 'search' OR NOT (data_type IS DISTINCT FROM 'text')",
            name="ck_special_equipment_attributes_search_text",
            postgresql_not_valid=True,
        ),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_special_equipment_attributes_lock_version",
        ),
        sa.Index(
            "idx_special_equipment_attributes_group",
            "attribute_group_id",
            "name",
            "id",
        ),
        sa.Index("idx_se_attributes_unit", "unit_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    attribute_group_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_attribute_groups.id",
            name="fk_special_equipment_attributes_group",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    data_type: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_units.id", ondelete="RESTRICT"),
        nullable=True,
    )
    filter_kind: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    lock_version: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, default=1, server_default=sa.text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class SpecialEquipmentAttributeOption(Base):
    __tablename__ = "special_equipment_attribute_options"
    __table_args__ = (
        sa.UniqueConstraint(
            "attribute_id",
            "code",
            name="uq_special_equipment_attribute_options_attribute_code",
        ),
        sa.UniqueConstraint(
            "attribute_id",
            "id",
            name="uq_se_attribute_options_attribute_id_id",
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_special_equipment_attribute_options_sort_order",
        ),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_special_equipment_attribute_options_lock_version",
        ),
        sa.Index(
            "idx_special_equipment_attribute_options_attribute",
            "attribute_id",
            "sort_order",
            "id",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_attributes.id",
            name="fk_special_equipment_attribute_options_attribute",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    lock_version: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, default=1, server_default=sa.text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class SpecialEquipmentColor(Base):
    """Managed color dictionary for special-equipment body/interior fields."""

    __tablename__ = "special_equipment_colors"
    __table_args__ = (
        sa.CheckConstraint(
            "applicability IN ('body', 'interior', 'both')",
            name="ck_special_equipment_colors_applicability",
        ),
        sa.CheckConstraint(
            "lock_version >= 1", name="ck_special_equipment_colors_lock_version"
        ),
        sa.Index(
            "uq_special_equipment_colors_code_norm",
            sa.text("lower(TRIM(BOTH FROM code))"),
            unique=True,
        ),
        sa.Index(
            "uq_special_equipment_colors_name_norm",
            sa.text("lower(TRIM(BOTH FROM name))"),
            unique=True,
        ),
        sa.Index(
            "idx_special_equipment_colors_active_select",
            "is_active",
            "applicability",
            sa.text("lower(name)"),
            "id",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    applicability: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    lock_version: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, default=1, server_default=sa.text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class SpecialEquipmentCategoryAttribute(Base):
    """One grouped characteristic configuration for a selected category."""

    __tablename__ = "special_equipment_category_attributes"
    __table_args__ = (
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_special_equipment_category_attributes_sort_order",
        ),
    )

    category_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_categories.id",
            name="fk_special_equipment_category_attributes_category",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_attributes.id",
            name="fk_special_equipment_category_attributes_attribute",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_attribute_groups.id",
            name="fk_special_equipment_category_attributes_group",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    is_required: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    is_filterable: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    is_visible: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    sort_order: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )


class SpecialEquipmentModificationAttributeValue(Base):
    """One live typed characteristic value owned by a modification."""

    __tablename__ = "special_equipment_modification_attribute_values"
    __table_args__ = (
        sa.CheckConstraint(
            "num_nonnulls(value_number, value_text, value_boolean, option_id) = 1",
            name="ck_se_modification_attribute_values_one_value",
        ),
        sa.CheckConstraint(
            "value_text IS NULL OR octet_length(value_text) <= 2000",
            name="ck_se_modification_attribute_values_text_size",
        ),
        sa.Index(
            "idx_se_modification_attribute_values_number",
            "attribute_id",
            "value_number",
            "modification_id",
            postgresql_where=sa.text("value_number IS NOT NULL"),
        ),
        sa.Index(
            "idx_se_modification_attribute_values_option",
            "attribute_id",
            "option_id",
            "modification_id",
            postgresql_where=sa.text("option_id IS NOT NULL"),
        ),
        sa.Index(
            "idx_se_modification_attribute_values_text_search",
            sa.func.lower(sa.column("value_text")).label("value_text_search"),
            postgresql_using="gin",
            postgresql_ops={"value_text_search": "gin_trgm_ops"},
            postgresql_where=sa.text("value_text IS NOT NULL"),
        ),
    )

    modification_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_modifications.id",
            name="fk_se_modification_attribute_values_modification",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_attributes.id",
            name="fk_se_modification_attribute_values_attribute",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    option_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_attribute_options.id",
            name="fk_se_modification_attribute_values_option",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    value_number: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 4), nullable=True
    )
    value_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)


class SpecialEquipmentProduct(Base):
    """One advertised unit; directory data stays live through modification."""

    __tablename__ = "special_equipment_products"
    __table_args__ = (
        sa.UniqueConstraint("code", name="uq_special_equipment_products_code"),
        sa.UniqueConstraint("slug", name="uq_special_equipment_products_slug"),
        sa.ForeignKeyConstraint(
            ["trim_id", "modification_id"],
            [
                "special_equipment_trims.id",
                "special_equipment_trims.modification_id",
            ],
            name="fk_se_products_trim_modification",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        sa.CheckConstraint(
            "price IS NULL OR price > 0",
            name="ck_special_equipment_products_price_nonnegative",
        ),
        sa.CheckConstraint(
            "special_price IS NULL OR (price IS NOT NULL "
            "AND special_price > 0 AND special_price < price)",
            name="ck_se_products_special_price_valid",
        ),
        sa.CheckConstraint(
            "price_from IS NULL OR price_from > 0",
            name="ck_se_products_price_from_valid",
        ),
        sa.CheckConstraint(
            "price_on_request OR price_from IS NULL",
            name="ck_se_products_price_mode_valid",
        ),
        sa.CheckConstraint(
            "mileage_km IS NULL OR mileage_km >= 0",
            name="ck_special_equipment_products_mileage_nonnegative",
        ),
        sa.CheckConstraint(
            "engine_hours IS NULL OR engine_hours >= 0",
            name="ck_special_equipment_products_engine_hours_nonnegative",
        ),
        sa.CheckConstraint(
            "currency_code = 'RUB'",
            name="ck_special_equipment_products_currency_rub",
        ),
        sa.CheckConstraint(
            "manufacture_year IS NULL OR manufacture_year BETWEEN 1900 AND 2200",
            name="ck_special_equipment_products_manufacture_year",
        ),
        sa.CheckConstraint(
            "condition IN ('new', 'used')",
            name="ck_special_equipment_products_condition",
        ),
        sa.CheckConstraint(
            "owners_count IS NULL OR owners_count >= 0",
            name="ck_special_equipment_products_owners_count_nonnegative",
            postgresql_not_valid=True,
        ),
        sa.CheckConstraint(
            "(condition = 'new' AND owners_count IS NULL) OR "
            "(condition = 'used' AND owners_count IS NOT NULL "
            "AND owners_count >= 0)",
            name="ck_special_equipment_products_condition_owners",
            postgresql_not_valid=True,
        ),
        sa.CheckConstraint(
            "(condition = 'new' AND mileage_km IS NULL AND engine_hours IS NULL) "
            "OR (condition = 'used' AND num_nonnulls(mileage_km, engine_hours) = 1)",
            name="ck_special_equipment_products_condition_usage",
        ),
        sa.CheckConstraint(
            "publication_status IN ('draft', 'published', 'archived')",
            name="ck_special_equipment_products_publication_status",
        ),
        sa.CheckConstraint(
            "sale_status IN ("
            "'available', 'on_order', 'reserved', 'sold', 'unavailable')",
            name="ck_special_equipment_products_sale_status",
        ),
        sa.CheckConstraint(
            "sale_status <> 'on_order' OR "
            "price_on_request OR "
            "(NOT price_on_request AND price > 0)",
            name="ck_special_equipment_products_on_order_price",
        ),
        sa.CheckConstraint(
            "(no_vin AND vin IS NULL AND chassis_vin IS NULL AND superstructure_vin IS NULL) OR "
            "(NOT no_vin AND vin IS NOT NULL AND btrim(vin) <> '' "
            "AND char_length(vin) <= 32)",
            name="ck_special_equipment_products_vin_choice",
        ),
        sa.CheckConstraint(
            "publication_status <> 'published' OR published_at IS NOT NULL",
            name="ck_special_equipment_products_published_at",
        ),
        sa.CheckConstraint(
            "publication_status <> 'published' OR seller_company_id IS NOT NULL",
            name="ck_special_equipment_products_published_seller",
        ),
        # A request-priced unit without ``price_from`` may be claimed only on the
        # strength of an allocation with an agreed positive price. That is a
        # cross-table rule, enforced by trigger ``se_product_claimed_price_guard``.
        sa.CheckConstraint(
            "sale_status NOT IN ('reserved', 'sold') OR "
            "price_on_request OR price IS NOT NULL",
            name="ck_special_equipment_products_claimed_price",
        ),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_special_equipment_products_lock_version",
        ),
        sa.Index(
            "idx_special_equipment_products_modification",
            "modification_id",
            sa.desc("updated_at"),
            sa.desc("id"),
        ),
        sa.Index(
            "idx_se_products_trim",
            "trim_id",
            sa.desc("updated_at"),
            sa.desc("id"),
        ),
        sa.Index(
            "idx_special_equipment_products_published",
            sa.desc("published_at"),
            sa.desc("id"),
            postgresql_where=sa.text("publication_status = 'published'"),
        ),
        sa.Index(
            "idx_special_equipment_products_price_published",
            "price",
            "id",
            postgresql_where=sa.text("publication_status = 'published'"),
        ),
        sa.Index(
            "idx_se_products_effective_price_published",
            # Match pg_get_expr's CASE layout; Alembic retains its newlines.
            sa.text(
                "(\nCASE\n    WHEN price_on_request THEN price_from\n"
                "    ELSE COALESCE(special_price, price)\nEND)"
            ),
            "id",
            postgresql_where=sa.text("publication_status = 'published'"),
        ),
        sa.Index(
            "idx_se_products_public_availability",
            "sale_status",
            sa.desc("published_at"),
            sa.desc("id"),
            postgresql_where=sa.text(
                "publication_status = 'published' "
                "AND sale_status IN ('available', 'on_order')"
            ),
        ),
        sa.Index(
            "idx_se_products_published_sale_status",
            "sale_status",
            "id",
            postgresql_where=sa.text("publication_status = 'published'"),
        ),
        sa.Index(
            "idx_se_products_description_search",
            sa.func.lower(sa.column("description")).label("description_search"),
            postgresql_using="gin",
            postgresql_ops={"description_search": "gin_trgm_ops"},
            postgresql_where=sa.text("description IS NOT NULL"),
        ),
        sa.Index(
            "idx_se_products_claimed_seller",
            "seller_company_id",
            "id",
            postgresql_where=sa.text(
                "seller_company_id IS NOT NULL "
                "AND sale_status IN ('reserved', 'sold')"
            ),
        ),
        sa.Index(
            "idx_se_products_body_color",
            "body_color_id",
            postgresql_where=sa.text("body_color_id IS NOT NULL"),
        ),
        sa.Index(
            "idx_se_products_interior_color",
            "interior_color_id",
            postgresql_where=sa.text("interior_color_id IS NOT NULL"),
        ),
        sa.Index(
            "idx_se_products_warehouse",
            "warehouse_id",
            "id",
            postgresql_where=sa.text("warehouse_id IS NOT NULL"),
        ),
        sa.ForeignKeyConstraint(
            ["modification_id", "model_id"],
            [
                "special_equipment_modifications.id",
                "special_equipment_modifications.model_id",
            ],
            name="fk_se_products_modification_model",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["superstructure_modification_id", "superstructure_model_id"],
            [
                "special_equipment_modifications.id",
                "special_equipment_modifications.model_id",
            ],
            name="fk_se_products_superstructure_modification_model",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "id",
            "superstructure_id",
            name="uq_special_equipment_products_id_superstructure",
        ),
        sa.CheckConstraint(
            "superstructure_source_product_id IS NULL OR superstructure_source_product_id <> id",
            name="ck_se_products_superstructure_source_not_self",
        ),
        sa.CheckConstraint(
            """
            (superstructure_id IS NULL AND modification_id IS NOT NULL AND model_id IS NULL
               AND superstructure_modification_id IS NULL
               AND superstructure_name IS NULL AND superstructure_manufacturer IS NULL
               AND superstructure_model_id IS NULL
               AND superstructure_source_product_id IS NULL)
            OR
            (superstructure_id IS NOT NULL AND modification_id IS NOT NULL AND model_id IS NULL
               AND superstructure_modification_id IS NULL
               AND superstructure_name IS NULL AND superstructure_manufacturer IS NULL
               AND superstructure_model_id IS NULL
               AND superstructure_source_product_id IS NULL)
            OR
            (superstructure_id IS NOT NULL AND model_id IS NOT NULL AND trim_id IS NULL
               AND superstructure_name IS NOT NULL AND btrim(superstructure_name) <> ''
               AND superstructure_manufacturer IS NOT NULL AND btrim(superstructure_manufacturer) <> ''
               AND (no_vin OR (chassis_vin IS NOT NULL AND btrim(chassis_vin) <> '')))
            """,
            name="ck_se_products_kind",
        ),
        sa.Index(
            "idx_se_products_superstructure",
            "superstructure_id",
            sa.desc("updated_at"),
            sa.desc("id"),
        ),
        sa.Index(
            "idx_se_products_superstructure_model",
            "superstructure_model_id",
            sa.desc("updated_at"),
            sa.desc("id"),
        ),
        sa.Index(
            "idx_se_products_superstructure_source",
            "superstructure_source_product_id",
            postgresql_where=sa.text("superstructure_source_product_id IS NOT NULL"),
        ),
        sa.Index(
            "idx_se_products_model",
            "model_id",
            sa.desc("updated_at"),
            sa.desc("id"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    modification_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_modifications.id",
            name="fk_special_equipment_products_modification",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_models.id", ondelete="RESTRICT"),
        nullable=True,
    )
    superstructure_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_superstructures.id", ondelete="RESTRICT"),
        nullable=True,
    )
    superstructure_model_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_models.id", ondelete="RESTRICT"),
        nullable=True,
    )
    superstructure_modification_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_modifications.id", ondelete="RESTRICT"),
        nullable=True,
    )
    superstructure_source_product_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_products.id",
            name="fk_se_products_superstructure_source",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    superstructure_name: Mapped[str | None] = mapped_column(
        sa.String(255), nullable=True
    )
    superstructure_manufacturer: Mapped[str | None] = mapped_column(
        sa.String(255), nullable=True
    )
    trim_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    seller_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "companies.id",
            name="fk_special_equipment_products_seller_company",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "warehouses.id",
            name="fk_se_products_warehouse",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    body_color_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_colors.id",
            name="fk_special_equipment_products_body_color",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    interior_color_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_colors.id",
            name="fk_special_equipment_products_interior_color",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=True,
    )
    slug: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    special_price: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    price_on_request: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        server_default=sa.false(),
    )
    price_from: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    currency_code: Mapped[str] = mapped_column(
        sa.CHAR(3), nullable=False, default="RUB", server_default=sa.text("'RUB'")
    )
    manufacture_year: Mapped[int | None] = mapped_column(sa.SmallInteger, nullable=True)
    vin: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    chassis_vin: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    superstructure_vin: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    no_vin: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    condition: Mapped[str] = mapped_column(
        sa.String(10), nullable=False, default="used", server_default=sa.text("'used'")
    )
    owners_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    mileage_km: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    engine_hours: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    publication_status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default="draft",
        server_default=sa.text("'draft'"),
    )
    sale_status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default="unavailable",
        server_default=sa.text("'unavailable'"),
    )
    published_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    lock_version: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, default=1, server_default=sa.text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    complectation_id = synonym("modification_id")
    dealer_id = synonym("seller_company_id")
    status = synonym("sale_status")

    @property
    def is_available(self) -> bool:
        return self.sale_status == "available"

    @is_available.setter
    def is_available(self, value: bool) -> None:
        self.sale_status = "available" if value else "unavailable"

    @property
    def images(self) -> list[str]:
        return getattr(self, "_images_cache", [])

    @images.setter
    def images(self, value: list[str]) -> None:
        self._images_cache = value

    @property
    def mark_id(self) -> Any:
        return getattr(self, "_mark_id_cache", None)

    @mark_id.setter
    def mark_id(self, value: Any) -> None:
        self._mark_id_cache = value


sa.Index(
    "uq_special_equipment_products_vin",
    sa.func.upper(SpecialEquipmentProduct.vin),
    unique=True,
    postgresql_where=sa.text("vin IS NOT NULL"),
)


class SpecialEquipmentProductCategory(Base):
    """A product may be advertised in every compatible category."""

    __tablename__ = "special_equipment_product_categories"
    __table_args__ = (
        sa.Index(
            "idx_special_equipment_product_categories_category",
            "category_id",
            "product_id",
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_products.id",
            name="fk_special_equipment_product_categories_product",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_categories.id",
            name="fk_special_equipment_product_categories_category",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )


class SpecialEquipmentProductAttachment(Base):
    """An ordered compatible attachment advertised for one product."""

    __tablename__ = "special_equipment_product_attachments"
    __table_args__ = (
        sa.CheckConstraint(
            "product_id <> attachment_product_id",
            name="ck_se_product_attachments_not_self",
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_se_product_attachments_position_nonnegative",
        ),
        sa.UniqueConstraint(
            "product_id",
            "position",
            name="uq_se_product_attachments_product_position",
        ),
        sa.Index(
            "idx_se_product_attachments_attachment",
            "attachment_product_id",
            "product_id",
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_products.id",
            name="fk_se_product_attachments_product",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    attachment_product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_products.id",
            name="fk_se_product_attachments_attachment_product",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default=sa.text("0"),
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            name="fk_se_product_attachments_created_by",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


class SpecialEquipmentProductImage(Base):
    """Ordered product gallery; storage identifiers stay private."""

    __tablename__ = "special_equipment_product_images"
    __table_args__ = (
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_special_equipment_product_images_sort_order_nonnegative",
        ),
        sa.Index(
            "uq_special_equipment_product_image_order",
            "product_id",
            "sort_order",
            unique=True,
        ),
        sa.Index(
            "uq_special_equipment_product_primary_image",
            "product_id",
            unique=True,
            postgresql_where=sa.text("is_primary"),
        ),
        sa.Index(
            "ix_special_equipment_product_images_product_id_source_ref",
            "product_id",
            "source_ref",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_products.id",
            name="fk_special_equipment_product_images_product",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    alt_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    is_primary: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    source_ref: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class SpecialEquipmentProductChassisValue(Base):
    """Chassis characteristic values for kit products without modification."""

    __tablename__ = "special_equipment_product_chassis_values"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["attribute_id", "option_id"],
            [
                "special_equipment_attribute_options.attribute_id",
                "special_equipment_attribute_options.id",
            ],
            name="fk_se_product_chassis_values_option_attribute",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "num_nonnulls(value_number, value_text, value_boolean, option_id) = 1",
            name="ck_se_product_chassis_values_one_value",
        ),
        sa.CheckConstraint(
            "value_text IS NULL OR octet_length(value_text) <= 2000",
            name="ck_se_product_chassis_values_text_size",
        ),
        sa.Index(
            "idx_se_product_chassis_values_number",
            "attribute_id",
            "value_number",
            "product_id",
            postgresql_where=sa.text("value_number IS NOT NULL"),
        ),
        sa.Index(
            "idx_se_product_chassis_values_option",
            "attribute_id",
            "option_id",
            "product_id",
            postgresql_where=sa.text("option_id IS NOT NULL"),
        ),
        sa.Index(
            "idx_se_product_chassis_values_text_search",
            sa.func.lower(sa.column("value_text")).label("value_text_search"),
            postgresql_using="gin",
            postgresql_ops={"value_text_search": "gin_trgm_ops"},
            postgresql_where=sa.text("value_text IS NOT NULL"),
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_products.id", ondelete="CASCADE"),
        primary_key=True,
    )
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_attributes.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    option_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    value_number: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 4), nullable=True
    )
    value_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)


class SpecialEquipmentProductSuperstructureValue(Base):
    """Superstructure characteristic values for kit products."""

    __tablename__ = "special_equipment_product_superstructure_values"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["product_id", "superstructure_id"],
            [
                "special_equipment_products.id",
                "special_equipment_products.superstructure_id",
            ],
            name="fk_se_product_superstructure_values_product",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["superstructure_id", "attribute_id"],
            [
                "special_equipment_superstructure_attributes.superstructure_id",
                "special_equipment_superstructure_attributes.attribute_id",
            ],
            name="fk_se_product_superstructure_values_assignment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["attribute_id", "option_id"],
            [
                "special_equipment_attribute_options.attribute_id",
                "special_equipment_attribute_options.id",
            ],
            name="fk_se_product_superstructure_values_option_attribute",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "num_nonnulls(value_number, value_text, value_boolean, option_id) = 1",
            name="ck_se_product_superstructure_values_one_value",
        ),
        sa.CheckConstraint(
            "value_text IS NULL OR octet_length(value_text) <= 2000",
            name="ck_se_product_superstructure_values_text_size",
        ),
        sa.Index(
            "idx_se_product_superstructure_values_number",
            "attribute_id",
            "value_number",
            "product_id",
            postgresql_where=sa.text("value_number IS NOT NULL"),
        ),
        sa.Index(
            "idx_se_product_superstructure_values_option",
            "attribute_id",
            "option_id",
            "product_id",
            postgresql_where=sa.text("option_id IS NOT NULL"),
        ),
        sa.Index(
            "idx_se_product_superstructure_values_text_search",
            sa.func.lower(sa.column("value_text")).label("value_text_search"),
            postgresql_using="gin",
            postgresql_ops={"value_text_search": "gin_trgm_ops"},
            postgresql_where=sa.text("value_text IS NOT NULL"),
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )
    superstructure_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    option_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    value_number: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 4), nullable=True
    )
    value_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)


class SpecialEquipmentCatalogDeletionLog(Base):
    """Immutable audit log of cascade deletions performed in the special equipment catalog."""

    __tablename__ = "special_equipment_catalog_deletion_log"
    __table_args__ = (
        sa.Index("idx_se_catalog_deletion_log_created_at", "created_at"),
        sa.Index("idx_se_catalog_deletion_log_root", "root_type", "root_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    root_type: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    root_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    root_code: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    root_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    catalog_revision: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    )


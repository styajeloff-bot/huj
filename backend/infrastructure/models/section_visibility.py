"""ORM model for explicit section visibility overrides."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class SectionVisibility(Base):
    """One explicit visibility override for an application scope and section."""

    __tablename__ = "section_visibility"
    __table_args__ = (
        sa.Index(
            "uq_section_visibility_storefront_scope_section",
            "storefront_id",
            "scope",
            "section_key",
            unique=True,
            postgresql_where=sa.text(
                "scope IN ('public', 'leasing_company', 'dealer', 'distributor') "
                "AND storefront_id IS NOT NULL"
            ),
        ),
        sa.Index(
            "uq_section_visibility_global_scope_section",
            "scope",
            "section_key",
            unique=True,
            postgresql_where=sa.text(
                "scope = 'carcraft_employee' AND storefront_id IS NULL"
            ),
        ),
        sa.CheckConstraint(
            "scope IN ('public', 'carcraft_employee', 'leasing_company', "
            "'dealer', 'distributor')",
            name="ck_section_visibility_scope",
        ),
        sa.CheckConstraint(
            "(scope IN ('public', 'leasing_company', 'dealer', 'distributor') "
            "AND storefront_id IS NOT NULL) OR "
            "(scope = 'carcraft_employee' AND storefront_id IS NULL)",
            name="ck_section_visibility_storefront_target",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    scope: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    storefront_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "catalog_storefronts.id",
            name="fk_section_visibility_storefront_id",
            ondelete="CASCADE",
        ),
        nullable=True,
    )
    section_key: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    is_visible: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=True,
        server_default=sa.true(),
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            name="fk_section_visibility_updated_by",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    )

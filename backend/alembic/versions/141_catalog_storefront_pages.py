"""Storefront constructor pages, revisions, and templates.

Revision ID: 141
Revises: 140
Create Date: 2026-09-30 07:30:00
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "141"
down_revision: str | None = "140"
branch_labels: str | None = None
depends_on: str | None = None


def _make_template_classic_leasing() -> dict:
    return {
        "settings": {
            "title": "Классический лизинг",
            "meta_description": "Выгодные программы лизинга легкового, грузового транспорта и спецтехники для бизнеса.",
            "primary_color": "#3367BD",
            "background_color": "#F9FAFB",
            "surface_color": "#FFFFFF",
            "text_color": "#111827",
            "border_radius": "medium",
        },
        "sections": [
            {
                "id": str(uuid.uuid4()),
                "name": "Главный баннер",
                "layout_type": "full_width",
                "styles": {
                    "padding_top": "64px",
                    "padding_bottom": "64px",
                    "background_color": "#1E293B",
                },
                "columns": [
                    {
                        "id": str(uuid.uuid4()),
                        "width": 12,
                        "widgets": [
                            {
                                "id": str(uuid.uuid4()),
                                "type": "hero_banner",
                                "is_hidden": False,
                                "props": {
                                    "title": "Лизинг транспорта и спецтехники для бизнеса",
                                    "subtitle": "Одобрение за 1 день. Аванс от 0%, срок до 60 месяцев, специальные субсидии от производителей.",
                                    "cta_text": "Рассчитать лизинг",
                                    "cta_link": "#leasing-calculator",
                                    "badge": "Субсидии до 15%",
                                    "background_overlay": 0.4,
                                },
                                "styles": {"text_align": "center"},
                            }
                        ],
                    }
                ],
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Лизинговый калькулятор",
                "layout_type": "container",
                "styles": {
                    "padding_top": "48px",
                    "padding_bottom": "48px",
                    "background_color": "transparent",
                },
                "columns": [
                    {
                        "id": str(uuid.uuid4()),
                        "width": 12,
                        "widgets": [
                            {
                                "id": str(uuid.uuid4()),
                                "type": "leasing_calculator",
                                "is_hidden": False,
                                "props": {
                                    "title": "Рассчитайте ежемесячный платеж",
                                    "default_cost": 5000000,
                                    "min_term": 12,
                                    "max_term": 60,
                                    "min_advance": 10,
                                    "max_advance": 50,
                                    "show_apply_button": True,
                                },
                                "styles": {},
                            }
                        ],
                    }
                ],
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Преимущества",
                "layout_type": "container",
                "styles": {
                    "padding_top": "48px",
                    "padding_bottom": "48px",
                    "background_color": "#FFFFFF",
                },
                "columns": [
                    {
                        "id": str(uuid.uuid4()),
                        "width": 12,
                        "widgets": [
                            {
                                "id": str(uuid.uuid4()),
                                "type": "features_grid",
                                "is_hidden": False,
                                "props": {
                                    "title": "Почему выбирают Carcraft",
                                    "columns_count": 3,
                                    "items": [
                                        {
                                            "title": "Решение за 15 минут",
                                            "description": "Автоматическая предварительная оценка без сбора десятков справок.",
                                            "icon": "lightning-bolt",
                                        },
                                        {
                                            "title": "Единая заявка",
                                            "description": "Отправьте запрос сразу в ведущие лизинговые компании страны.",
                                            "icon": "document-duplicate",
                                        },
                                        {
                                            "title": "Скидки от дилеров",
                                            "description": "Прямые контракты с производителями и спецтехника из наличия.",
                                            "icon": "tag",
                                        },
                                    ],
                                },
                                "styles": {},
                            }
                        ],
                    }
                ],
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Каталог спецтехники",
                "layout_type": "container",
                "styles": {
                    "padding_top": "48px",
                    "padding_bottom": "48px",
                    "background_color": "transparent",
                },
                "columns": [
                    {
                        "id": str(uuid.uuid4()),
                        "width": 12,
                        "widgets": [
                            {
                                "id": str(uuid.uuid4()),
                                "type": "product_showcase",
                                "is_hidden": False,
                                "props": {
                                    "title": "Популярная техника в наличии",
                                    "limit": 8,
                                    "view_mode": "grid",
                                    "show_all_link": "/special-equipment",
                                },
                                "styles": {},
                            }
                        ],
                    }
                ],
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Часто задаваемые вопросы",
                "layout_type": "container",
                "styles": {
                    "padding_top": "48px",
                    "padding_bottom": "48px",
                    "background_color": "#FFFFFF",
                },
                "columns": [
                    {
                        "id": str(uuid.uuid4()),
                        "width": 12,
                        "widgets": [
                            {
                                "id": str(uuid.uuid4()),
                                "type": "faq_accordion",
                                "is_hidden": False,
                                "props": {
                                    "title": "Вопросы и ответы",
                                    "expand_first": True,
                                    "items": [
                                        {
                                            "question": "Кто может оформить технику в лизинг?",
                                            "answer": "Юридические лица и индивидуальные предприниматели, зарегистрированные от 6 месяцев.",
                                        },
                                        {
                                            "question": "Какие документы требуются для заявки?",
                                            "answer": "Для экспресс-оценки достаточно ИНН компании, паспорта руководителя и карточки организации.",
                                        },
                                        {
                                            "question": "Возможен ли лизинг с нулевым авансом?",
                                            "answer": "Да, для надежных компаний с положительной финансовой историей действуют программы с авансом 0%.",
                                        },
                                    ],
                                },
                                "styles": {},
                            }
                        ],
                    }
                ],
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Контакты и реквизиты",
                "layout_type": "container",
                "styles": {
                    "padding_top": "48px",
                    "padding_bottom": "48px",
                    "background_color": "transparent",
                },
                "columns": [
                    {
                        "id": str(uuid.uuid4()),
                        "width": 12,
                        "widgets": [
                            {
                                "id": str(uuid.uuid4()),
                                "type": "contacts_block",
                                "is_hidden": False,
                                "props": {
                                    "title": "Контакты",
                                    "show_phone": True,
                                    "show_email": True,
                                    "show_address": True,
                                    "show_requisites": True,
                                },
                                "styles": {},
                            }
                        ],
                    }
                ],
            },
        ],
    }


def _make_template_equipment_showcase() -> dict:
    return {
        "settings": {
            "title": "Каталожная витрина спецтехники",
            "meta_description": "Большой каталог спецтехники и коммерческого транспорта в наличии и под заказ.",
            "primary_color": "#2563EB",
            "background_color": "#F8FAFC",
            "surface_color": "#FFFFFF",
            "text_color": "#0F172A",
            "border_radius": "medium",
        },
        "sections": [
            {
                "id": str(uuid.uuid4()),
                "name": "Баннер каталога",
                "layout_type": "container",
                "styles": {
                    "padding_top": "56px",
                    "padding_bottom": "40px",
                    "background_color": "transparent",
                },
                "columns": [
                    {
                        "id": str(uuid.uuid4()),
                        "width": 12,
                        "widgets": [
                            {
                                "id": str(uuid.uuid4()),
                                "type": "hero_banner",
                                "is_hidden": False,
                                "props": {
                                    "title": "Каталог спецтехники и коммерческого транспорта",
                                    "subtitle": "Прямые поставки от официальных дилеров со складов по всей России.",
                                    "cta_text": "Перейти к каталогу",
                                    "cta_link": "#equipment-catalog",
                                },
                                "styles": {},
                            }
                        ],
                    }
                ],
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Витрина спецтехники",
                "layout_type": "container",
                "styles": {
                    "padding_top": "32px",
                    "padding_bottom": "48px",
                    "background_color": "transparent",
                },
                "columns": [
                    {
                        "id": str(uuid.uuid4()),
                        "width": 12,
                        "widgets": [
                            {
                                "id": str(uuid.uuid4()),
                                "type": "product_showcase",
                                "is_hidden": False,
                                "props": {
                                    "title": "Техника на складах",
                                    "limit": 12,
                                    "view_mode": "grid",
                                },
                                "styles": {},
                            }
                        ],
                    }
                ],
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Заявка на индивидуальный подбор",
                "layout_type": "container",
                "styles": {
                    "padding_top": "48px",
                    "padding_bottom": "48px",
                    "background_color": "#FFFFFF",
                },
                "columns": [
                    {
                        "id": str(uuid.uuid4()),
                        "width": 12,
                        "widgets": [
                            {
                                "id": str(uuid.uuid4()),
                                "type": "lead_form",
                                "is_hidden": False,
                                "props": {
                                    "title": "Не нашли подходящую технику?",
                                    "subtitle": "Оставьте заявку, и мы подберем технику по вашим параметрам в течение дня.",
                                    "button_text": "Подобрать технику",
                                    "show_inn": True,
                                    "show_category_select": True,
                                },
                                "styles": {},
                            }
                        ],
                    }
                ],
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Партнеры и лизингодатели",
                "layout_type": "container",
                "styles": {
                    "padding_top": "40px",
                    "padding_bottom": "40px",
                    "background_color": "transparent",
                },
                "columns": [
                    {
                        "id": str(uuid.uuid4()),
                        "width": 12,
                        "widgets": [
                            {
                                "id": str(uuid.uuid4()),
                                "type": "partners_carousel",
                                "is_hidden": False,
                                "props": {
                                    "title": "Партнеры платформы",
                                    "items": [],
                                },
                                "styles": {},
                            }
                        ],
                    }
                ],
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Контакты",
                "layout_type": "container",
                "styles": {
                    "padding_top": "40px",
                    "padding_bottom": "40px",
                    "background_color": "#FFFFFF",
                },
                "columns": [
                    {
                        "id": str(uuid.uuid4()),
                        "width": 12,
                        "widgets": [
                            {
                                "id": str(uuid.uuid4()),
                                "type": "contacts_block",
                                "is_hidden": False,
                                "props": {
                                    "title": "Отдел продаж и консультаций",
                                    "show_phone": True,
                                    "show_email": True,
                                    "show_address": True,
                                },
                                "styles": {},
                            }
                        ],
                    }
                ],
            },
        ],
    }


def _make_template_promo_landing() -> dict:
    return {
        "settings": {
            "title": "Лизинговый промо-лендинг",
            "meta_description": "Специальные условия лизинга для юридических лиц и ИП: скидки, субсидии, быстрое оформление.",
            "primary_color": "#059669",
            "background_color": "#F0FDF4",
            "surface_color": "#FFFFFF",
            "text_color": "#064E3B",
            "border_radius": "medium",
        },
        "sections": [
            {
                "id": str(uuid.uuid4()),
                "name": "Промо-баннер",
                "layout_type": "full_width",
                "styles": {
                    "padding_top": "72px",
                    "padding_bottom": "72px",
                    "background_color": "#064E3B",
                },
                "columns": [
                    {
                        "id": str(uuid.uuid4()),
                        "width": 12,
                        "widgets": [
                            {
                                "id": str(uuid.uuid4()),
                                "type": "hero_banner",
                                "is_hidden": False,
                                "props": {
                                    "title": "Специальное предложение на лизинг 2026",
                                    "subtitle": "Сниженная процентная ставка и субсидия до 500 000 ₽ на первую единицу техники.",
                                    "cta_text": "Зафиксировать условия",
                                    "cta_link": "#promo-form",
                                    "badge": "Ограниченное предложение",
                                },
                                "styles": {"text_align": "center"},
                            }
                        ],
                    }
                ],
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Экспресс-калькулятор",
                "layout_type": "container",
                "styles": {
                    "padding_top": "48px",
                    "padding_bottom": "48px",
                    "background_color": "transparent",
                },
                "columns": [
                    {
                        "id": str(uuid.uuid4()),
                        "width": 12,
                        "widgets": [
                            {
                                "id": str(uuid.uuid4()),
                                "type": "leasing_calculator",
                                "is_hidden": False,
                                "props": {
                                    "title": "Экспресс-расчет платежа с субсидией",
                                    "default_cost": 3500000,
                                    "min_term": 12,
                                    "max_term": 48,
                                    "min_advance": 0,
                                    "max_advance": 40,
                                    "show_apply_button": True,
                                },
                                "styles": {},
                            }
                        ],
                    }
                ],
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Преимущества акции",
                "layout_type": "container",
                "styles": {
                    "padding_top": "48px",
                    "padding_bottom": "48px",
                    "background_color": "#FFFFFF",
                },
                "columns": [
                    {
                        "id": str(uuid.uuid4()),
                        "width": 12,
                        "widgets": [
                            {
                                "id": str(uuid.uuid4()),
                                "type": "features_grid",
                                "is_hidden": False,
                                "props": {
                                    "title": "Что входит в акцию",
                                    "columns_count": 3,
                                    "items": [
                                        {
                                            "title": "Аванс 0%",
                                            "description": "Возможность забрать технику без первоначального взноса.",
                                            "icon": "badge-percent",
                                        },
                                        {
                                            "title": "КАСКО в подарок",
                                            "description": "Страхование на первый год включено в договор лизинга.",
                                            "icon": "shield-check",
                                        },
                                        {
                                            "title": "Доставка до базы",
                                            "description": "Бережная доставка техники прямо на вашу рабочую площадку.",
                                            "icon": "truck",
                                        },
                                    ],
                                },
                                "styles": {},
                            }
                        ],
                    }
                ],
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Конверсионная плашка",
                "layout_type": "full_width",
                "styles": {
                    "padding_top": "40px",
                    "padding_bottom": "40px",
                    "background_color": "#047857",
                },
                "columns": [
                    {
                        "id": str(uuid.uuid4()),
                        "width": 12,
                        "widgets": [
                            {
                                "id": str(uuid.uuid4()),
                                "type": "cta_strip",
                                "is_hidden": False,
                                "props": {
                                    "title": "Акция действует до конца текущего месяца",
                                    "subtitle": "Забронируйте ставку и условия сейчас — договор можно заключить позже.",
                                    "button_text": "Забронировать ставку",
                                    "button_link": "#promo-form",
                                },
                                "styles": {"text_align": "center"},
                            }
                        ],
                    }
                ],
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Форма заявки",
                "layout_type": "container",
                "styles": {
                    "padding_top": "48px",
                    "padding_bottom": "48px",
                    "background_color": "transparent",
                },
                "columns": [
                    {
                        "id": str(uuid.uuid4()),
                        "width": 12,
                        "widgets": [
                            {
                                "id": str(uuid.uuid4()),
                                "type": "lead_form",
                                "is_hidden": False,
                                "props": {
                                    "title": "Зафиксировать условия акции",
                                    "subtitle": "Менеджер свяжется с вами в течение 10 минут и закрепит персональную скидку.",
                                    "button_text": "Отправить заявку",
                                    "show_inn": True,
                                    "show_category_select": False,
                                },
                                "styles": {},
                            }
                        ],
                    }
                ],
            },
        ],
    }


def upgrade() -> None:
    # 1. catalog_storefront_pages
    op.create_table(
        "catalog_storefront_pages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "storefront_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "catalog_storefronts.id",
                ondelete="CASCADE",
                name="fk_catalog_storefront_pages_storefront_id",
            ),
            nullable=False,
        ),
        sa.Column("page_key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=True),
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "draft_layout",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "published_layout",
            postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                ondelete="SET NULL",
                name="fk_catalog_storefront_pages_updated_by",
            ),
            nullable=True,
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.CheckConstraint(
            "version > 0",
            name="ck_catalog_storefront_pages_version",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published')",
            name="ck_catalog_storefront_pages_status",
        ),
        sa.UniqueConstraint(
            "storefront_id",
            "page_key",
            name="uq_catalog_storefront_pages_storefront_page_key",
        ),
    )
    op.create_index(
        "idx_catalog_storefront_pages_storefront_slug",
        "catalog_storefront_pages",
        ["storefront_id", "slug"],
    )

    # 2. catalog_storefront_page_revisions
    op.create_table(
        "catalog_storefront_page_revisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "page_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "catalog_storefront_pages.id",
                ondelete="CASCADE",
                name="fk_catalog_storefront_page_revisions_page_id",
            ),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("summary", sa.String(length=255), nullable=True),
        sa.Column("layout_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                ondelete="SET NULL",
                name="fk_catalog_storefront_page_revisions_created_by",
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index(
        "idx_catalog_storefront_page_revisions_page_version",
        "catalog_storefront_page_revisions",
        ["page_id", "version"],
    )

    # 3. catalog_storefront_templates
    templates_table = op.create_table(
        "catalog_storefront_templates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "category",
            sa.String(length=64),
            nullable=False,
            server_default="general",
        ),
        sa.Column("preview_image_url", sa.String(length=512), nullable=True),
        sa.Column("layout", postgresql.JSONB(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.UniqueConstraint(
            "code",
            name="uq_catalog_storefront_templates_code",
        ),
    )

    # Seed initial templates
    templates_data = [
        {
            "id": uuid.uuid4(),
            "code": "classic-leasing",
            "name": "Классический лизинг",
            "description": "Сбалансированный шаблон витрины: промо-баннер, калькулятор, преимущества, витрина техники, FAQ и контакты.",
            "category": "leasing",
            "preview_image_url": None,
            "layout": _make_template_classic_leasing(),
            "is_active": True,
        },
        {
            "id": uuid.uuid4(),
            "code": "equipment-showcase",
            "name": "Каталожная витрина спецтехники",
            "description": "Акцент на каталог техники, быстрый подбор и форму заявки.",
            "category": "showcase",
            "preview_image_url": None,
            "layout": _make_template_equipment_showcase(),
            "is_active": True,
        },
        {
            "id": uuid.uuid4(),
            "code": "promo-landing",
            "name": "Лизинговый промо-лендинг",
            "description": "Высококонверсионный одностраничник для маркетинговых кампаний и спецпредложений.",
            "category": "promo",
            "preview_image_url": None,
            "layout": _make_template_promo_landing(),
            "is_active": True,
        },
    ]

    op.bulk_insert(templates_table, templates_data)


def downgrade() -> None:
    op.drop_table("catalog_storefront_templates")
    op.drop_table("catalog_storefront_page_revisions")
    op.drop_table("catalog_storefront_pages")

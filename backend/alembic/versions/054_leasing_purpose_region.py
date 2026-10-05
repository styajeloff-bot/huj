"""leasing purpose and region dictionaries

Revision ID: 054
Revises: 053
Create Date: 2026-06-18 11:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None

PURPOSES = [
        {'purpose_name': 'business', 'purpose_display_name': 'Для предпринимательской деятельности'},
        {'purpose_name': 'personal', 'purpose_display_name': 'Личное пользование'},
        {'purpose_name': 'management', 'purpose_display_name': 'Для руководства'},
        {'purpose_name': 'staff', 'purpose_display_name': 'Для служебных поездок'},
        {'purpose_name': 'taxi', 'purpose_display_name': 'Для такси'},
        {'purpose_name': 'test_drive', 'purpose_display_name': 'Для тест-драйва'},
        {'purpose_name': 'other', 'purpose_display_name': 'Прочее'}
]

REGIONS = [
        {'region_name': 'r001', 'region_display_name': 'Адыгея'},
        {'region_name': 'r002', 'region_display_name': 'Алтай'},
        {'region_name': 'r003', 'region_display_name': 'Алтайский край'},
        {'region_name': 'r004', 'region_display_name': 'Амурская область'},
        {'region_name': 'r005', 'region_display_name': 'Архангельская область'},
        {'region_name': 'r006', 'region_display_name': 'Астраханская область'},
        {'region_name': 'r007', 'region_display_name': 'Башкортостан'},
        {'region_name': 'r008', 'region_display_name': 'Белгородская область'},
        {'region_name': 'r009', 'region_display_name': 'Брянская область'},
        {'region_name': 'r010', 'region_display_name': 'Бурятия'},
        {'region_name': 'r011', 'region_display_name': 'Владимирская область'},
        {'region_name': 'r012', 'region_display_name': 'Волгоградская область'},
        {'region_name': 'r013', 'region_display_name': 'Вологодская область'},
        {'region_name': 'r014', 'region_display_name': 'Воронежская область'},
        {'region_name': 'r015', 'region_display_name': 'Дагестан'},
        {'region_name': 'r016', 'region_display_name': 'Донецкая Народная Республика'},
        {'region_name': 'r017', 'region_display_name': 'Еврейская автономная область'},
        {'region_name': 'r018', 'region_display_name': 'Забайкальский край'},
        {'region_name': 'r019', 'region_display_name': 'Запорожская область'},
        {'region_name': 'r020', 'region_display_name': 'Ивановская область'},
        {'region_name': 'r021', 'region_display_name': 'Ингушетия'},
        {'region_name': 'r022', 'region_display_name': 'Иркутская область'},
        {'region_name': 'r023', 'region_display_name': 'Кабардино-Балкария'},
        {'region_name': 'r024', 'region_display_name': 'Калининградская область'},
        {'region_name': 'r025', 'region_display_name': 'Калмыкия'},
        {'region_name': 'r026', 'region_display_name': 'Калужская область'},
        {'region_name': 'r027', 'region_display_name': 'Камчатский край'},
        {'region_name': 'r028', 'region_display_name': 'Карачаево-Черкесия'},
        {'region_name': 'r029', 'region_display_name': 'Карелия'},
        {'region_name': 'r030', 'region_display_name': 'Кемеровская область — Кузбасс'},
        {'region_name': 'r031', 'region_display_name': 'Кировская область'},
        {'region_name': 'r032', 'region_display_name': 'Коми'},
        {'region_name': 'r033', 'region_display_name': 'Костромская область'},
        {'region_name': 'r034', 'region_display_name': 'Краснодарский край'},
        {'region_name': 'r035', 'region_display_name': 'Красноярский край'},
        {'region_name': 'r036', 'region_display_name': 'Крым'},
        {'region_name': 'r037', 'region_display_name': 'Курганская область'},
        {'region_name': 'r038', 'region_display_name': 'Курская область'},
        {'region_name': 'r039', 'region_display_name': 'Ленинградская область'},
        {'region_name': 'r040', 'region_display_name': 'Липецкая область'},
        {'region_name': 'r041', 'region_display_name': 'Луганская Народная Республика'},
        {'region_name': 'r042', 'region_display_name': 'Магаданская область'},
        {'region_name': 'r043', 'region_display_name': 'Марий Эл'},
        {'region_name': 'r044', 'region_display_name': 'Мордовия'},
        {'region_name': 'r045', 'region_display_name': 'Москва'},
        {'region_name': 'r046', 'region_display_name': 'Московская область'},
        {'region_name': 'r047', 'region_display_name': 'Мурманская область'},
        {'region_name': 'r048', 'region_display_name': 'Ненецкий автономный округ'},
        {'region_name': 'r049', 'region_display_name': 'Нижегородская область'},
        {'region_name': 'r050', 'region_display_name': 'Новгородская область'},
        {'region_name': 'r051', 'region_display_name': 'Новосибирская область'},
        {'region_name': 'r052', 'region_display_name': 'Омская область'},
        {'region_name': 'r053', 'region_display_name': 'Оренбургская область'},
        {'region_name': 'r054', 'region_display_name': 'Орловская область'},
        {'region_name': 'r055', 'region_display_name': 'Пензенская область'},
        {'region_name': 'r056', 'region_display_name': 'Пермский край'},
        {'region_name': 'r057', 'region_display_name': 'Приморский край'},
        {'region_name': 'r058', 'region_display_name': 'Псковская область'},
        {'region_name': 'r059', 'region_display_name': 'Ростовская область'},
        {'region_name': 'r060', 'region_display_name': 'Рязанская область'},
        {'region_name': 'r061', 'region_display_name': 'Самарская область'},
        {'region_name': 'r062', 'region_display_name': 'Санкт-Петербург'},
        {'region_name': 'r063', 'region_display_name': 'Саратовская область'},
        {'region_name': 'r064', 'region_display_name': 'Саха (Якутия)'},
        {'region_name': 'r065', 'region_display_name': 'Сахалинская область'},
        {'region_name': 'r066', 'region_display_name': 'Свердловская область'},
        {'region_name': 'r067', 'region_display_name': 'Севастополь'},
        {'region_name': 'r068', 'region_display_name': 'Северная Осетия — Алания'},
        {'region_name': 'r069', 'region_display_name': 'Смоленская область'},
        {'region_name': 'r070', 'region_display_name': 'Ставропольский край'},
        {'region_name': 'r071', 'region_display_name': 'Тамбовская область'},
        {'region_name': 'r072', 'region_display_name': 'Татарстан'},
        {'region_name': 'r073', 'region_display_name': 'Тверская область'},
        {'region_name': 'r074', 'region_display_name': 'Томская область'},
        {'region_name': 'r075', 'region_display_name': 'Тульская область'},
        {'region_name': 'r076', 'region_display_name': 'Тыва'},
        {'region_name': 'r077', 'region_display_name': 'Тюменская область'},
        {'region_name': 'r078', 'region_display_name': 'Удмуртия'},
        {'region_name': 'r079', 'region_display_name': 'Ульяновская область'},
        {'region_name': 'r080', 'region_display_name': 'Хабаровский край'},
        {'region_name': 'r081', 'region_display_name': 'Хакасия'},
        {'region_name': 'r082', 'region_display_name': 'Ханты-Мансийский автономный округ — Югра'},
        {'region_name': 'r083', 'region_display_name': 'Херсонская область'},
        {'region_name': 'r084', 'region_display_name': 'Челябинская область'},
        {'region_name': 'r085', 'region_display_name': 'Чечня'},
        {'region_name': 'r086', 'region_display_name': 'Чувашия'},
        {'region_name': 'r087', 'region_display_name': 'Чукотский автономный округ'},
        {'region_name': 'r088', 'region_display_name': 'Ямало-Ненецкий автономный округ'},
        {'region_name': 'r089', 'region_display_name': 'Ярославская область'}
]


def upgrade() -> None:
    op.create_table(
        "leasing_purpose",
        sa.Column("purpose_name", sa.String(length=64), nullable=False),
        sa.Column("purpose_display_name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("purpose_name"),
    )
    op.create_table(
        "leasing_region",
        sa.Column("region_name", sa.String(length=64), nullable=False),
        sa.Column("region_display_name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("region_name"),
        sa.UniqueConstraint("region_display_name", name="uq_leasing_region_display_name"),
    )
    op.create_index(
        "idx_leasing_region_display_name",
        "leasing_region",
        ["region_display_name"],
    )
    op.add_column(
        "application_vehicles",
        sa.Column("leasing_purpose", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "application_vehicles",
        sa.Column(
            "regions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.bulk_insert(sa.table(
        "leasing_purpose",
        sa.column("purpose_name", sa.String),
        sa.column("purpose_display_name", sa.String),
    ), PURPOSES)
    op.bulk_insert(sa.table(
        "leasing_region",
        sa.column("region_name", sa.String),
        sa.column("region_display_name", sa.String),
    ), REGIONS)


def downgrade() -> None:
    op.drop_column("application_vehicles", "regions")
    op.drop_column("application_vehicles", "leasing_purpose")
    op.drop_index("idx_leasing_region_display_name", table_name="leasing_region")
    op.drop_table("leasing_region")
    op.drop_table("leasing_purpose")

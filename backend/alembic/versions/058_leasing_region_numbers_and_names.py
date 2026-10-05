"""leasing region numbers and full display names

Revision ID: 058
Revises: 057
Create Date: 2026-06-19 13:45:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None

REGIONS = [
    {"region_name": "Adygeya_Respublika", "region_display_name": "Республика Адыгея", "region_number": "01"},
    {"region_name": "Bashkortostan_Respublika", "region_display_name": "Республика Башкортостан", "region_number": "02"},
    {"region_name": "Buryatia_Respublika", "region_display_name": "Республика Бурятия", "region_number": "03"},
    {"region_name": "Altai_Respublika", "region_display_name": "Республика Алтай", "region_number": "04"},
    {"region_name": "Dagestan_Respublika", "region_display_name": "Республика Дагестан", "region_number": "05"},
    {"region_name": "Ingushetia_Respublika", "region_display_name": "Республика Ингушетия", "region_number": "06"},
    {"region_name": "Kabardino_Balkarian_Respublika", "region_display_name": "Кабардино-Балкарская Республика", "region_number": "07"},
    {"region_name": "Kalmykia_Respublika", "region_display_name": "Республика Калмыкия", "region_number": "08"},
    {"region_name": "Karachaevo_Cherkess_Respublika", "region_display_name": "Карачаево-Черкесская Республика", "region_number": "09"},
    {"region_name": "Karelia_Respublika", "region_display_name": "Республика Карелия", "region_number": "10"},
    {"region_name": "Komi_Respublika", "region_display_name": "Республика Коми", "region_number": "11"},
    {"region_name": "Mari_El_Respublika", "region_display_name": "Республика Марий Эл", "region_number": "12"},
    {"region_name": "Mordovia_Respublika", "region_display_name": "Республика Мордовия", "region_number": "13"},
    {"region_name": "Sakha_Yakutia_Respublika", "region_display_name": "Республика Саха (Якутия)", "region_number": "14"},
    {"region_name": "North_Ossetia_Respublika", "region_display_name": "Республика Северная Осетия — Алания", "region_number": "15"},
    {"region_name": "Tatarstan_Respublika", "region_display_name": "Республика Татарстан", "region_number": "16"},
    {"region_name": "Tyva_Respublika", "region_display_name": "Республика Тыва", "region_number": "17"},
    {"region_name": "Udmurt_Respublika", "region_display_name": "Удмуртская Республика", "region_number": "18"},
    {"region_name": "Khakassia_Respublika", "region_display_name": "Республика Хакасия", "region_number": "19"},
    {"region_name": "Chechen_Respublika", "region_display_name": "Чеченская Республика", "region_number": "20"},
    {"region_name": "Chuvash_Respublika", "region_display_name": "Чувашская Республика", "region_number": "21"},
    {"region_name": "Altai_Krai", "region_display_name": "Алтайский край", "region_number": "22"},
    {"region_name": "Krasnodar_Krai", "region_display_name": "Краснодарский край", "region_number": "23"},
    {"region_name": "Krasnoyarsk_Krai", "region_display_name": "Красноярский край", "region_number": "24"},
    {"region_name": "Primorsky_Krai", "region_display_name": "Приморский край", "region_number": "25"},
    {"region_name": "Stavropol_Krai", "region_display_name": "Ставропольский край", "region_number": "26"},
    {"region_name": "Khabarovsk_Krai", "region_display_name": "Хабаровский край", "region_number": "27"},
    {"region_name": "Amur_Oblast", "region_display_name": "Амурская область", "region_number": "28"},
    {"region_name": "Arkhangelsk_Oblast", "region_display_name": "Архангельская область", "region_number": "29"},
    {"region_name": "Astrakhan_Oblast", "region_display_name": "Астраханская область", "region_number": "30"},
    {"region_name": "Belgorod_Oblast", "region_display_name": "Белгородская область", "region_number": "31"},
    {"region_name": "Bryansk_Oblast", "region_display_name": "Брянская область", "region_number": "32"},
    {"region_name": "Vladimir_Oblast", "region_display_name": "Владимирская область", "region_number": "33"},
    {"region_name": "Volgograd_Oblast", "region_display_name": "Волгоградская область", "region_number": "34"},
    {"region_name": "Vologda_Oblast", "region_display_name": "Вологодская область", "region_number": "35"},
    {"region_name": "Voronezh_Oblast", "region_display_name": "Воронежская область", "region_number": "36"},
    {"region_name": "Ivanovo_Oblast", "region_display_name": "Ивановская область", "region_number": "37"},
    {"region_name": "Irkutsk_Oblast", "region_display_name": "Иркутская область", "region_number": "38"},
    {"region_name": "Kaliningrad_Oblast", "region_display_name": "Калининградская область", "region_number": "39"},
    {"region_name": "Kaluga_Oblast", "region_display_name": "Калужская область", "region_number": "40"},
    {"region_name": "Kamchatka_Krai", "region_display_name": "Камчатский край", "region_number": "41"},
    {"region_name": "Kemerovo_Oblast", "region_display_name": "Кемеровская область", "region_number": "42"},
    {"region_name": "Kirov_Oblast", "region_display_name": "Кировская область", "region_number": "43"},
    {"region_name": "Kostroma_Oblast", "region_display_name": "Костромская область", "region_number": "44"},
    {"region_name": "Kurgan_Oblast", "region_display_name": "Курганская область", "region_number": "45"},
    {"region_name": "Kursk_Oblast", "region_display_name": "Курская область", "region_number": "46"},
    {"region_name": "Leningrad_Oblast", "region_display_name": "Ленинградская область", "region_number": "47"},
    {"region_name": "Lipetsk_Oblast", "region_display_name": "Липецкая область", "region_number": "48"},
    {"region_name": "Magadan_Oblast", "region_display_name": "Магаданская область", "region_number": "49"},
    {"region_name": "Moscow_Oblast", "region_display_name": "Московская область", "region_number": "50"},
    {"region_name": "Murmansk_Oblast", "region_display_name": "Мурманская область", "region_number": "51"},
    {"region_name": "Nizhny_Novgorod_Oblast", "region_display_name": "Нижегородская область", "region_number": "52"},
    {"region_name": "Novgorod_Oblast", "region_display_name": "Новгородская область", "region_number": "53"},
    {"region_name": "Novosibirsk_Oblast", "region_display_name": "Новосибирская область", "region_number": "54"},
    {"region_name": "Omsk_Oblast", "region_display_name": "Омская область", "region_number": "55"},
    {"region_name": "Orenburg_Oblast", "region_display_name": "Оренбургская область", "region_number": "56"},
    {"region_name": "Orel_Oblast", "region_display_name": "Орловская область", "region_number": "57"},
    {"region_name": "Penza_Oblast", "region_display_name": "Пензенская область", "region_number": "58"},
    {"region_name": "Perm_Krai", "region_display_name": "Пермский край", "region_number": "59"},
    {"region_name": "Pskov_Oblast", "region_display_name": "Псковская область", "region_number": "60"},
    {"region_name": "Rostov_Oblast", "region_display_name": "Ростовская область", "region_number": "61"},
    {"region_name": "Ryazan_Oblast", "region_display_name": "Рязанская область", "region_number": "62"},
    {"region_name": "Samara_Oblast", "region_display_name": "Самарская область", "region_number": "63"},
    {"region_name": "Saratov_Oblast", "region_display_name": "Саратовская область", "region_number": "64"},
    {"region_name": "Sakhalin_Oblast", "region_display_name": "Сахалинская область", "region_number": "65"},
    {"region_name": "Sverdlovsk_Oblast", "region_display_name": "Свердловская область", "region_number": "66"},
    {"region_name": "Smolensk_Oblast", "region_display_name": "Смоленская область", "region_number": "67"},
    {"region_name": "Tambov_Oblast", "region_display_name": "Тамбовская область", "region_number": "68"},
    {"region_name": "Tver_Oblast", "region_display_name": "Тверская область", "region_number": "69"},
    {"region_name": "Tomsk_Oblast", "region_display_name": "Томская область", "region_number": "70"},
    {"region_name": "Tula_Oblast", "region_display_name": "Тульская область", "region_number": "71"},
    {"region_name": "Tyumen_Oblast", "region_display_name": "Тюменская область", "region_number": "72"},
    {"region_name": "Ulyanovsk_Oblast", "region_display_name": "Ульяновская область", "region_number": "73"},
    {"region_name": "Chelyabinsk_Oblast", "region_display_name": "Челябинская область", "region_number": "74"},
    {"region_name": "Zabaykalsky_Krai", "region_display_name": "Забайкальский край", "region_number": "75"},
    {"region_name": "Yaroslavl_Oblast", "region_display_name": "Ярославская область", "region_number": "76"},
    {"region_name": "Moscow", "region_display_name": "г. Москва", "region_number": "77"},
    {"region_name": "Saint_Petersburg", "region_display_name": "г. Санкт-Петербург", "region_number": "78"},
    {"region_name": "Jewish_Autonomous_Oblast", "region_display_name": "Еврейская автономная область", "region_number": "79"},
    {"region_name": "Donetsk_Peoples_Republic", "region_display_name": "Донецкая Народная Республика", "region_number": "80"},
    {"region_name": "Lugansk_Peoples_Republic", "region_display_name": "Луганская Народная Республика", "region_number": "81"},
    {"region_name": "Crimea_Respublika", "region_display_name": "Республика Крым", "region_number": "82"},
    {"region_name": "Nenets_Autonomous_Okrug", "region_display_name": "Ненецкий автономный округ", "region_number": "83"},
    {"region_name": "Kherson_Oblast", "region_display_name": "Херсонская область", "region_number": "84"},
    {"region_name": "Zaporozhye_Oblast", "region_display_name": "Запорожская область", "region_number": "85"},
    {"region_name": "Khanty_Mansiysk_Autonomous_Okrug", "region_display_name": "Ханты-Мансийский автономный округ — Югра", "region_number": "86"},
    {"region_name": "Chukotka_Autonomous_Okrug", "region_display_name": "Чукотский автономный округ", "region_number": "87"},
    {"region_name": "Yamalo_Nenets_Autonomous_Okrug", "region_display_name": "Ямало-Ненецкий автономный округ", "region_number": "89"},
    {"region_name": "Sevastopol", "region_display_name": "г. Севастополь", "region_number": "92"},
]

REGION_DISPLAY_RENAMES = {
    "Адыгея": "Республика Адыгея",
    "Алтай": "Республика Алтай",
    "Башкортостан": "Республика Башкортостан",
    "Бурятия": "Республика Бурятия",
    "Дагестан": "Республика Дагестан",
    "Ингушетия": "Республика Ингушетия",
    "Кабардино-Балкария": "Кабардино-Балкарская Республика",
    "Калмыкия": "Республика Калмыкия",
    "Карачаево-Черкесия": "Карачаево-Черкесская Республика",
    "Карелия": "Республика Карелия",
    "Коми": "Республика Коми",
    "Марий Эл": "Республика Марий Эл",
    "Мордовия": "Республика Мордовия",
    "Москва": "г. Москва",
    "Санкт-Петербург": "г. Санкт-Петербург",
    "Саха (Якутия)": "Республика Саха (Якутия)",
    "Северная Осетия — Алания": "Республика Северная Осетия — Алания",
    "Татарстан": "Республика Татарстан",
    "Тыва": "Республика Тыва",
    "Удмуртия": "Удмуртская Республика",
    "Хакасия": "Республика Хакасия",
    "Чечня": "Чеченская Республика",
    "Чувашия": "Чувашская Республика",
}


def _regions_table() -> sa.TableClause:
    return sa.table(
        "leasing_region",
        sa.column("region_name", sa.String),
        sa.column("region_display_name", sa.String),
        sa.column("region_number", sa.String),
    )


def upgrade() -> None:
    op.add_column(
        "leasing_region",
        sa.Column("region_number", sa.String(length=2), nullable=True),
    )
    op.execute("DELETE FROM leasing_region")
    op.bulk_insert(_regions_table(), REGIONS)
    op.alter_column("leasing_region", "region_number", nullable=False)
    op.create_unique_constraint(
        "uq_leasing_region_number",
        "leasing_region",
        ["region_number"],
    )
    op.create_index(
        "idx_leasing_region_number",
        "leasing_region",
        ["region_number"],
    )

    if REGION_DISPLAY_RENAMES:
        values_sql = ", ".join(
            "(" + ", ".join(sa.text(repr(value)).text for value in pair) + ")"
            for pair in REGION_DISPLAY_RENAMES.items()
        )
        op.execute(
            f"""
            UPDATE application_vehicles
            SET regions = COALESCE((
                SELECT jsonb_agg(COALESCE(rename.new_value, item.value) ORDER BY item.ordinality)
                FROM jsonb_array_elements_text(regions) WITH ORDINALITY AS item(value, ordinality)
                LEFT JOIN (VALUES {values_sql}) AS rename(old_value, new_value)
                    ON rename.old_value = item.value
            ), '[]'::jsonb)
            WHERE regions IS NOT NULL
            """
        )


def downgrade() -> None:
    op.drop_index("idx_leasing_region_number", table_name="leasing_region")
    op.drop_constraint("uq_leasing_region_number", "leasing_region", type_="unique")
    op.drop_column("leasing_region", "region_number")

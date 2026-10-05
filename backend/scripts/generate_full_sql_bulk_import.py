"""Generate crash-safe bulk SQL artifacts for full import datasets.

The script intentionally does not connect to Postgres or ClickHouse. It reads
the full export CSV/XLSX files and emits deterministic data files plus SQL
loaders that can be reviewed, copied into containers, and re-run.
"""
# ruff: noqa: S608

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FASTAPI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FASTAPI_ROOT))

from infrastructure.services.catalog_parser import (  # noqa: E402
    OPTIONS_MAPPING,
    SPECIFICATIONS_MAPPING,
    ParsedRow,
    extract_row_data,
)

DEFAULT_FULL_DIR = PROJECT_ROOT / "leasing_export" / "import" / "full"
DEFAULT_CATALOG_DIR = DEFAULT_FULL_DIR / "catalog_real_stock_capped_2500000"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "leasing_export" / "import" / "bulk_sql"

APPLICATION_STATUS_VALUES = {"active", "rejected", "issued"}
LCA_STATUS_VALUES = {
    "submitted",
    "under_review",
    "under_review_with_docs",
    "approved_scoring",
    "approved_scoring_another_cond",
    "rejected_prescoring",
    "documents_required",
    "approved_final",
    "approved_final_another_cond",
    "rejected_approved",
    "selected_lc",
    "deal",
    "closed",
}

NAMESPACE = uuid.UUID("f9c0e1b7-75d7-4f4d-8b32-e914210e6f4a")
CITY_NAMESPACE = uuid.uuid5(NAMESPACE, "cities")
VEHICLE_WAREHOUSE_NAMESPACE = uuid.uuid5(NAMESPACE, "vehicle_warehouses")
APPLICATION_VEHICLE_NAMESPACE = uuid.uuid5(NAMESPACE, "application_vehicles")
REFERENCE_NAMESPACE = uuid.uuid5(NAMESPACE, "reference_seed")

OPTION_COLUMNS = sorted(set(OPTIONS_MAPPING.values()))
SPECIFICATION_COLUMNS = sorted(set(SPECIFICATIONS_MAPPING.values()))


@dataclass(slots=True)
class BulkManifest:
    """Summary returned by :func:`generate_artifacts` and written to JSON."""

    generated_at: str
    source_files: dict[str, dict[str, str | int]]
    row_counts: dict[str, int] = field(default_factory=dict)
    anomalies: list[dict[str, str]] = field(default_factory=list)
    application_ids: set[str] = field(default_factory=set)


class TsvWriter:
    def __init__(self, path: Path, columns: list[str], manifest: BulkManifest) -> None:
        self.path = path
        self.columns = columns
        self.table_name = path.stem
        self.manifest = manifest
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file_obj = self.path.open("w", encoding="utf-8", newline="")
        self.manifest.row_counts.setdefault(self.table_name, 0)

    def write(self, row: Mapping[str, Any]) -> None:
        self.file_obj.write(
            "\t".join(_to_tsv_value(row.get(column)) for column in self.columns)
            + "\n"
        )
        self.manifest.row_counts[self.table_name] = (
            self.manifest.row_counts.get(self.table_name, 0) + 1
        )

    def close(self) -> None:
        self.file_obj.close()


@dataclass(slots=True)
class ExcelImagePool:
    by_mark_model: dict[tuple[str, str], list[str]]
    by_mark: dict[str, list[str]]
    all_images: list[str]

    def images_for(
        self,
        *,
        mark_name: str | None,
        model_name: str | None,
        vehicle_id: str,
    ) -> list[str]:
        if not self.all_images:
            return []
        mark_key = _image_key(mark_name)
        model_key = _image_key(model_name)
        candidates = self.by_mark_model.get((mark_key, model_key), [])
        if not candidates:
            candidates = self.by_mark.get(mark_key, [])
        if not candidates:
            candidates = self.all_images
        return [candidates[_stable_index(vehicle_id, len(candidates))]]


@dataclass(slots=True)
class ExcelCatalogTemplatePool:
    by_mark_model: dict[tuple[str, str], list[ParsedRow]]
    by_mark: dict[str, list[ParsedRow]]
    all_templates: list[ParsedRow]

    def template_for(
        self,
        *,
        mark_name: str | None,
        model_name: str | None,
        vehicle_id: str,
    ) -> ParsedRow | None:
        mark_key = _image_key(mark_name)
        model_key = _image_key(model_name)
        candidates = self.by_mark_model.get((mark_key, model_key), [])
        if not candidates:
            candidates = self.by_mark.get(mark_key, [])
        if not candidates:
            candidates = self.all_templates
        if not candidates:
            return None
        return candidates[_stable_index(vehicle_id, len(candidates))]


class JsonlWriter:
    def __init__(self, path: Path, manifest: BulkManifest) -> None:
        self.path = path
        self.table_name = path.stem
        self.manifest = manifest
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file_obj = self.path.open("w", encoding="utf-8", newline="")
        self.manifest.row_counts.setdefault(self.table_name, 0)

    def write(self, row: Mapping[str, Any]) -> None:
        self.file_obj.write(json.dumps(row, ensure_ascii=False, default=_json_default) + "\n")
        self.manifest.row_counts[self.table_name] = (
            self.manifest.row_counts.get(self.table_name, 0) + 1
        )

    def close(self) -> None:
        self.file_obj.close()


COMPANY_COLUMNS = [
    "id",
    "name",
    "inn",
    "kpp",
    "ogrn",
    "company_type",
    "address",
    "contact_info",
    "legal_address",
    "actual_address",
    "phone",
    "email",
    "website",
    "is_active",
    "full_name",
    "short_name",
    "okpo",
    "okato",
    "legal_form",
    "region",
    "city",
    "registration_date",
    "employees_count",
    "main_okved_code",
    "main_okved_description",
    "director_full_name",
    "bank_bik",
    "bank_name",
    "authorized_capital",
    "net_profit",
    "reporting_year",
    "tax_system",
    "enrichment_status",
    "created_at",
    "updated_at",
]

USER_COLUMNS = [
    "id",
    "email",
    "password_hash",
    "name",
    "role",
    "company_id",
    "phone",
    "is_active",
    "email_verified",
    "phone_verified",
    "created_at",
    "updated_at",
]

CITY_COLUMNS = ["id", "name", "created_at"]

WAREHOUSE_COLUMNS = [
    "id",
    "address",
    "brand",
    "city_id",
    "dealer_id",
    "company_id",
    "status",
    "created_at",
    "updated_at",
]

LINK_COLUMNS = ["distributor_company_id", "dealer_company_id", "created_at"]
LEASING_COMPANY_COLUMNS = ["id", "company_id", "is_active", "created_at", "updated_at"]

MARK_COLUMNS = ["id", "name", "cyrillic_name", "popular", "country"]
MODEL_COLUMNS = ["id", "name", "cyrillic_name", "class", "year_from", "year_to", "mark_id"]
GENERATION_COLUMNS = ["id", "name", "year_start", "year_stop", "is_restyle", "model_id"]
CONFIGURATION_COLUMNS = [
    "id",
    "doors_count",
    "body_type",
    "configuration_name",
    "generation_id",
]
MODIFICATION_COLUMNS = [
    "complectation_id",
    "offers_price_from",
    "offers_price_to",
    "group_name",
    "configuration_id",
]
OPTION_TSV_COLUMNS = ["complectation_id", *OPTION_COLUMNS]
SPECIFICATION_TSV_COLUMNS = ["complectation_id", *SPECIFICATION_COLUMNS]

VEHICLE_COLUMNS = [
    "id",
    "vin",
    "dealer_id",
    "mark_id",
    "model_id",
    "generation_id",
    "configuration_id",
    "complectation_id",
    "year",
    "base_price",
    "special_price",
    "dealer_cost",
    "discount_price",
    "color",
    "color_inter",
    "images",
    "status",
    "is_available",
    "created_at",
    "updated_at",
]

VEHICLE_WAREHOUSE_COLUMNS = ["id", "vehicle_id", "warehouse_id", "created_at"]

LEASING_APPLICATION_COLUMNS = [
    "id",
    "display_number",
    "company_id",
    "dealer_company_id",
    "vehicle_id",
    "name",
    "email",
    "status",
    "total_amount",
    "down_payment",
    "down_payment_percent",
    "lease_term_months",
    "monthly_payment",
    "total_cost",
    "markup",
    "rate",
    "selected_leasing_companies",
    "questionnaire_completed",
    "questionnaire_progress",
    "current_stage",
    "created_at",
    "updated_at",
]

LCA_COLUMNS = [
    "id",
    "application_id",
    "leasing_company_id",
    "status",
    "submitted_at",
    "created_at",
    "updated_at",
]

APPLICATION_VEHICLE_COLUMNS = [
    "id",
    "application_id",
    "vehicle_id",
    "modification_id",
    "quantity",
    "unit_price",
    "total_price",
    "vin",
    "is_model_order",
    "created_at",
    "updated_at",
]

EXCHANGE_REQUEST_COLUMNS = [
    "id",
    "lc_user_id",
    "vehicle_id",
    "distributor_id",
    "quantity",
    "expiration_date",
    "discount_type",
    "discount_value",
    "file_url",
    "file_name",
    "status",
    "accepted_bid_id",
    "batch_number",
    "batch_index",
    "created_at",
    "updated_at",
]

EXCHANGE_BID_COLUMNS = [
    "id",
    "request_id",
    "dealer_id",
    "distributor_id",
    "price",
    "comment",
    "is_accepted",
    "kp_file_url",
    "kp_file_name",
    "kp_status",
    "kp_dealer_comment",
    "kp_sent_at",
    "kp_responded_at",
    "quantity",
    "bid_file_url",
    "bid_file_name",
    "created_at",
    "updated_at",
]

REFERENCE_DOCUMENT_TYPES: list[dict[str, Any]] = [
    {
        "name": "Бухгалтерская отчётность",
        "type_code": "accounting_report_xml",
        "display_name": "Бухгалтерская отчётность",
        "description": "Отчётность нарастающим итогом в формате XML по стандарту 1С Бухгалтерия (только ОСН).",
        "file_types": [".xml"],
        "max_file_size_mb": 25,
        "auto_approve": False,
    },
    {
        "name": "Декларация по налогу на прибыль",
        "type_code": "profit_tax_declaration_xml",
        "display_name": "Декларация по налогу на прибыль",
        "description": "Отчётность нарастающим итогом в формате XML по стандарту 1С Бухгалтерия (только ОСН).",
        "file_types": [".xml"],
        "max_file_size_mb": 25,
        "auto_approve": False,
    },
    {
        "name": "Декларация по НДС",
        "type_code": "vat_declaration_xml",
        "display_name": "Декларация по НДС",
        "description": "Ежеквартальная отчётность в формате XML по стандарту 1С Бухгалтерия. Один файл на квартал.",
        "file_types": [".xml"],
        "max_file_size_mb": 25,
        "auto_approve": False,
    },
    {
        "name": "Декларация по УСН",
        "type_code": "usn_declaration_xml",
        "display_name": "Декларация по УСН",
        "description": "Годовая отчётность в формате XML по стандарту 1С Бухгалтерия (только УСН).",
        "file_types": [".xml"],
        "max_file_size_mb": 25,
        "auto_approve": False,
    },
    {
        "name": "Бухгалтерская отчётность (XML)",
        "type_code": "accounting_xml",
        "display_name": "Бухгалтерская отчётность (XML)",
        "description": "Экспорт бухгалтерской отчётности из 1С Бухгалтерия в формате XML",
        "file_types": [".xml"],
        "max_file_size_mb": 25,
        "auto_approve": True,
    },
]

REFERENCE_DEALER_OPTIONS = [
    "Доставка",
    "Шиномонтаж",
    "Установка телематики",
    "Коврики",
    "Постановка на учет в ГИБДД",
    "Сигнализация",
    "Зимняя резина",
    "Оклейка частичная",
    "Оклейка полная",
]

REFERENCE_CITIES = [
    "Москва",
    "Санкт-Петербург",
    "Нижний Новгород",
    "Краснодар",
    "Екатеринбург",
]

REFERENCE_REPORT_TYPES = [
    ("0710001", "0710001", "Бухгалтерский баланс", "Форма №1. Бухгалтерский баланс организации (ОКУД 0710001)"),
    ("0710002", "0710002", "Отчет о финансовых результатах", "Форма №2. Отчет о финансовых результатах (ОКУД 0710002)"),
    ("0710004", "0710004", "Отчет об изменениях капитала", "Форма №3. Отчет об изменениях капитала (ОКУД 0710004)"),
    ("0710005", "0710005", "Отчет о движении денежных средств", "Форма №4. Отчет о движении денежных средств (ОКУД 0710005)"),
    ("1151001", None, "Налоговая декларация по НДС", None),
    ("1152017", None, "Налоговая декларация по УСН", None),
    ("1151006", None, "Налоговая декларация по налогу на прибыль", None),
    ("0710099", None, "Пояснения к бухгалтерской отчетности", None),
]

REFERENCE_REPORT_CODES = [
    ("0710001", "1110", "ВнеоборотАктив", "Внеоборотные активы"),
    ("0710001", "1150", "ОсновнСредств", "Основные средства"),
    ("0710001", "1160", "НематАктив", "Нематериальные, финансовые и другие внеоборотные активы"),
    ("0710001", "1170", "ФинВлож", "Финансовые вложения"),
    ("0710001", "1210", "Запасы", "Запасы"),
    ("0710001", "1230", "ДебиторЗадолж", "Дебиторская задолженность"),
    ("0710001", "1250", "ДенежнСред", "Денежные средства и денежные эквиваленты"),
    ("0710001", "1600", "Баланс", "БАЛАНС (актив)"),
    ("0710001", "1310", "УставнКапитал", "Уставный капитал (складочный капитал, уставный фонд, вклады товарищей)"),
    ("0710001", "1410", "КредитЗадолж", "Кредиты и займы"),
    ("0710001", "1450", "КредитЗадолжКратк", "Кредиторская задолженность"),
    ("0710001", "1500", "КраткосрочнОбяз", "Краткосрочные обязательства"),
    ("0710001", "1700", "БалансПасс", "БАЛАНС (пассив)"),
    ("0710002", "2110", "Выручка", "Выручка"),
    ("0710002", "2120", "СебестПрод", "Себестоимость продаж"),
    ("0710002", "2200", "ПродажПрибыль", "Прибыль (убыток) от продаж"),
    ("0710002", "2210", "КомерРасход", "Коммерческие расходы"),
    ("0710002", "2220", "УправлРасход", "Управленческие расходы"),
    ("0710002", "2300", "ПрибыльДоНал", "Прибыль (убыток) до налогообложения"),
    ("0710002", "2340", "ПрочДоходы", "Прочие доходы"),
    ("0710002", "2350", "ПрочРасход", "Прочие расходы"),
    ("0710002", "2400", "ЧистПрибыль", "Чистая прибыль (убыток)"),
    ("0710004", "3100", "КапУст", "Уставный капитал"),
    ("0710004", "3200", "КапСобАкц", "Собственные выкупленные акции"),
    ("0710004", "3300", "КапДоб", "Добавочный капитал"),
    ("0710004", "3400", "КапРез", "Резервный капитал"),
    ("0710004", "3500", "КапНерПр", "Нераспределенная прибыль (непокрытый убыток)"),
    ("0710004", "3600", "КапНакДооц", "Накопленные дооценки"),
    ("0710004", "3700", "КапИтог", "Итого"),
    ("0710005", "4110", "ДенежнСредНач", "Денежные средства на начало периода"),
    ("0710005", "4111", "ПоступПрод", "Поступления от продаж товаров, выполнения работ, оказания услуг"),
    ("0710005", "4121", "ПлатПост", "Платежи поставщикам"),
    ("0710005", "4122", "ПлатПерс", "Платежи персоналу"),
    ("0710005", "4123", "ПлатПроч", "Прочие платежи"),
    ("0710005", "4100", "СальдоТек", "Сальдо денежных средств (текущая деятельность)"),
    ("0710005", "4210", "ПоступИнв", "Поступления по инвестиционной деятельности"),
    ("0710005", "4220", "ПлатИнв", "Платежи по инвестиционной деятельности"),
    ("0710005", "4200", "СальдоИнв", "Сальдо инвестиционной деятельности"),
    ("0710005", "4310", "ПоступФин", "Поступления по финансовой деятельности"),
    ("0710005", "4320", "ПлатФин", "Платежи по финансовой деятельности"),
    ("0710005", "4300", "СальдоФин", "Сальдо финансовой деятельности"),
    ("0710005", "4400", "СальдоПер", "Сальдо за отчетный период"),
    ("0710005", "4500", "ДенежнСредКон", "Денежные средства на конец периода"),
]

REFERENCE_NDS_TAX_RATES = [
    ("РеалТов20", "Налоговая база по ставке 20%", "Сумма налога по ставке 20%"),
    ("РеалТов10", "Налоговая база по ставке 10%", "Сумма налога по ставке 10%"),
    ("РеалТов7", "Налоговая база по ставке 7%", "Сумма налога по ставке 7%"),
    ("РеалТов5", "Налоговая база по ставке 5%", "Сумма налога по ставке 5%"),
    ("РеалТов120", "Налоговая база по ставке 20/120", "Сумма налога по ставке 20/120"),
    ("РеалТов110", "Налоговая база по ставке 10/110", "Сумма налога по ставке 10/110"),
    ("РеалТов107", "Налоговая база по ставке 7/107", "Сумма налога по ставке 7/107"),
    ("РеалТов105", "Налоговая база по ставке 5/105", "Сумма налога по ставке 5/105"),
    ("РеалТов18", "Налоговая база по ставке 18%", "Сумма налога по ставке 18%"),
    ("РеалТов118", "Налоговая база по ставке 18/118", "Сумма налога по ставке 18/118"),
    ("РеалТов16.67", "Налоговая база по ставке 16.67%", "Сумма налога по ставке 16.67%"),
    ("РеалТов9.09", "Налоговая база по ставке 9.09%", "Сумма налога по ставке 9.09%"),
    ("ВыпСтрРаб", "Налоговая база по СМР", "Сумма налога по СМР"),
    ("ОплПредПост", "Налоговая база по предоплате", "Сумма налога по предоплате"),
    ("РеалТов0", "Налоговая база по ставке 0%", "Сумма налога по ставке 0%"),
    (
        "РеалТовНалЮЛ",
        "Налоговая база по ставке для налогоплательщика - нерезидента",
        "Сумма налога по ставке для налогоплательщика - нерезидента",
    ),
]


def generate_artifacts(
    *,
    full_dir: Path = DEFAULT_FULL_DIR,
    catalog_dir: Path = DEFAULT_CATALOG_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    image_source_paths: Iterable[Path] | None = None,
    strict: bool = True,
) -> BulkManifest:
    """Generate Postgres and ClickHouse bulk-load artifacts."""

    full_dir = full_dir.resolve()
    catalog_dir = catalog_dir.resolve()
    output_dir = output_dir.resolve()
    image_sources = [path.resolve() for path in image_source_paths or []]
    _reset_output_dir(output_dir)

    now = _now()
    manifest = BulkManifest(
        generated_at=now,
        source_files=_source_file_manifest(full_dir, catalog_dir, image_sources),
        row_counts={},
        anomalies=[],
    )

    pg_data_dir = output_dir / "postgres" / "data"
    ch_data_dir = output_dir / "clickhouse" / "data"
    pg = _open_postgres_writers(pg_data_dir, manifest)
    ch = _open_clickhouse_writers(ch_data_dir, manifest)

    seen: dict[str, set[str]] = {
        "companies": set(),
        "users": set(),
        "cities": set(),
        "warehouses": set(),
        "links": set(),
        "leasing_companies": set(),
        "mark": set(),
        "model": set(),
        "generation": set(),
        "configuration": set(),
        "modification": set(),
        "options": set(),
        "specifications": set(),
        "vehicles": set(),
        "vehicle_warehouses": set(),
        "application_vehicles": set(),
        "exchange_requests": set(),
        "exchange_bids": set(),
    }
    companies_by_id: dict[str, dict[str, Any]] = {}
    vehicles_by_id: dict[str, dict[str, Any]] = {}
    applications: dict[str, dict[str, Any]] = {}
    application_lcs: dict[str, set[str]] = {}
    display_counters: dict[tuple[str, str], int] = {}
    leasing_company_ids: set[str] = set()

    try:
        _process_companies(full_dir, pg, ch, seen, companies_by_id, now)
        _process_users(full_dir, pg, ch, seen, now)
        _process_warehouses(full_dir, pg, seen, now)
        _process_distributor_links(full_dir, pg, seen, now)
        _process_catalog(
            full_dir,
            catalog_dir,
            pg,
            ch,
            seen,
            vehicles_by_id,
            manifest,
            strict,
            now,
            image_sources,
        )
        _process_lca(
            full_dir,
            pg,
            ch,
            seen,
            vehicles_by_id,
            companies_by_id,
            applications,
            application_lcs,
            display_counters,
            leasing_company_ids,
            manifest,
            strict,
            now,
        )
        _write_leasing_companies(pg, seen, leasing_company_ids, companies_by_id, now)
        _write_leasing_applications(pg, applications, application_lcs)
        _process_exchange_requests(full_dir, pg, ch, seen, vehicles_by_id, manifest, strict, now)
        _process_exchange_bids(full_dir, pg, ch, seen, manifest, now)
    finally:
        for tsv_writer in pg.values():
            tsv_writer.close()
        for jsonl_writer in ch.values():
            jsonl_writer.close()

    reference_seed_path = output_dir / "postgres" / "reference_seed.sql"
    _write_postgres_reference_seed_sql(reference_seed_path)
    _write_postgres_sql(output_dir / "postgres" / "load.sql", pg_data_dir, reference_seed_path)
    _write_clickhouse_sql(output_dir / "clickhouse" / "load.sql", ch_data_dir)
    _write_clickhouse_docker_loader(
        output_dir / "clickhouse" / "load_via_docker_compose.sh"
    )
    _write_manifest(output_dir / "manifest.json", manifest)
    return manifest


def _open_postgres_writers(
    data_dir: Path, manifest: BulkManifest
) -> dict[str, TsvWriter]:
    return {
        "companies": TsvWriter(data_dir / "companies.tsv", COMPANY_COLUMNS, manifest),
        "users": TsvWriter(data_dir / "users.tsv", USER_COLUMNS, manifest),
        "cities": TsvWriter(data_dir / "cities.tsv", CITY_COLUMNS, manifest),
        "warehouses": TsvWriter(data_dir / "warehouses.tsv", WAREHOUSE_COLUMNS, manifest),
        "distributor_dealer_links": TsvWriter(
            data_dir / "distributor_dealer_links.tsv", LINK_COLUMNS, manifest
        ),
        "leasing_companies": TsvWriter(
            data_dir / "leasing_companies.tsv", LEASING_COMPANY_COLUMNS, manifest
        ),
        "mark": TsvWriter(data_dir / "mark.tsv", MARK_COLUMNS, manifest),
        "model": TsvWriter(data_dir / "model.tsv", MODEL_COLUMNS, manifest),
        "generation": TsvWriter(data_dir / "generation.tsv", GENERATION_COLUMNS, manifest),
        "configuration": TsvWriter(
            data_dir / "configuration.tsv", CONFIGURATION_COLUMNS, manifest
        ),
        "modification": TsvWriter(
            data_dir / "modification.tsv", MODIFICATION_COLUMNS, manifest
        ),
        "options": TsvWriter(data_dir / "options.tsv", OPTION_TSV_COLUMNS, manifest),
        "specifications": TsvWriter(
            data_dir / "specifications.tsv", SPECIFICATION_TSV_COLUMNS, manifest
        ),
        "vehicles": TsvWriter(data_dir / "vehicles.tsv", VEHICLE_COLUMNS, manifest),
        "vehicle_warehouses": TsvWriter(
            data_dir / "vehicle_warehouses.tsv", VEHICLE_WAREHOUSE_COLUMNS, manifest
        ),
        "leasing_applications": TsvWriter(
            data_dir / "leasing_applications.tsv", LEASING_APPLICATION_COLUMNS, manifest
        ),
        "leasing_company_applications": TsvWriter(
            data_dir / "leasing_company_applications.tsv", LCA_COLUMNS, manifest
        ),
        "application_vehicles": TsvWriter(
            data_dir / "application_vehicles.tsv", APPLICATION_VEHICLE_COLUMNS, manifest
        ),
        "exchange_requests": TsvWriter(
            data_dir / "exchange_requests.tsv", EXCHANGE_REQUEST_COLUMNS, manifest
        ),
        "exchange_bids": TsvWriter(
            data_dir / "exchange_bids.tsv", EXCHANGE_BID_COLUMNS, manifest
        ),
    }


def _open_clickhouse_writers(
    data_dir: Path, manifest: BulkManifest
) -> dict[str, JsonlWriter]:
    return {
        "dwh_companies": JsonlWriter(data_dir / "dwh_companies.jsonl", manifest),
        "dwh_users": JsonlWriter(data_dir / "dwh_users.jsonl", manifest),
        "dwh_vehicles": JsonlWriter(data_dir / "dwh_vehicles.jsonl", manifest),
        "dwh_leasing_company_applications": JsonlWriter(
            data_dir / "dwh_leasing_company_applications.jsonl", manifest
        ),
        "dwh_application_vehicles": JsonlWriter(
            data_dir / "dwh_application_vehicles.jsonl", manifest
        ),
        "dwh_exchange_requests": JsonlWriter(
            data_dir / "dwh_exchange_requests.jsonl", manifest
        ),
        "dwh_exchange_bids": JsonlWriter(data_dir / "dwh_exchange_bids.jsonl", manifest),
    }


def _process_companies(
    full_dir: Path,
    pg: dict[str, TsvWriter],
    ch: dict[str, JsonlWriter],
    seen: dict[str, set[str]],
    companies_by_id: dict[str, dict[str, Any]],
    now: str,
) -> None:
    for filename in (
        "companies_clients.csv",
        "companies_distributor_dealer.csv",
        "companies.csv",
        "companies_dealers.csv",
    ):
        for row in _read_csv(full_dir / filename):
            company_id = _normalize_uuid(row.get("id"))
            if not company_id or company_id in seen["companies"]:
                continue
            company_type = _company_type(row.get("company_type"))
            company = {
                "id": company_id,
                "name": _string(row.get("name")) or f"Company {company_id}",
                "inn": _string(row.get("inn")),
                "kpp": _string(row.get("kpp")),
                "ogrn": _string(row.get("ogrn")),
                "company_type": company_type,
                "address": _json({"value": row.get("address")})
                if _string(row.get("address"))
                else None,
                "contact_info": None,
                "legal_address": _string(row.get("legal_address")),
                "actual_address": _string(row.get("actual_address")),
                "phone": _string(row.get("phone")),
                "email": _string(row.get("email")),
                "website": _string(row.get("website")),
                "is_active": _bool(row.get("is_active"), default=True),
                "full_name": _string(row.get("full_name")),
                "short_name": _string(row.get("short_name")),
                "okpo": _string(row.get("okpo")),
                "okato": _string(row.get("okato")),
                "legal_form": _string(row.get("legal_form")),
                "region": _string(row.get("region")),
                "city": _string(row.get("city")),
                "registration_date": _date(row.get("registration_date")),
                "employees_count": _int(row.get("employees_count")),
                "main_okved_code": _string(row.get("main_okved_code")),
                "main_okved_description": _string(row.get("main_okved_description")),
                "director_full_name": _string(row.get("director_full_name")),
                "bank_bik": _string(row.get("bank_bik")),
                "bank_name": _string(row.get("bank_name")),
                "authorized_capital": _int(row.get("authorized_capital")),
                "net_profit": _int(row.get("net_profit")),
                "reporting_year": _int(row.get("reporting_year")),
                "tax_system": _string(row.get("tax_system")),
                "enrichment_status": _string(row.get("enrichment_status")),
                "created_at": _datetime(row.get("created_at")) or now,
                "updated_at": _datetime(row.get("updated_at")) or now,
            }
            seen["companies"].add(company_id)
            companies_by_id[company_id] = company
            pg["companies"].write(company)
            ch["dwh_companies"].write(_dwh_company(company))


def _process_users(
    full_dir: Path,
    pg: dict[str, TsvWriter],
    ch: dict[str, JsonlWriter],
    seen: dict[str, set[str]],
    now: str,
) -> None:
    for row in _read_csv(full_dir / "users.csv"):
        user_id = _normalize_uuid(row.get("id"))
        if not user_id or user_id in seen["users"]:
            continue
        user = {
            "id": user_id,
            "email": _string(row.get("email")),
            "password_hash": _string(row.get("password_hash")),
            "name": _string(row.get("name")),
            "role": _user_role(row.get("role")),
            "company_id": _normalize_uuid(row.get("company_id")),
            "phone": _string(row.get("phone")) or f"+7000{len(seen['users']):07d}",
            "is_active": _bool(row.get("is_active"), default=True),
            "email_verified": _bool(row.get("email_verified"), default=False),
            "phone_verified": _bool(row.get("phone_verified"), default=True),
            "created_at": _datetime(row.get("created_at")) or now,
            "updated_at": _datetime(row.get("updated_at")) or now,
        }
        seen["users"].add(user_id)
        pg["users"].write(user)
        ch["dwh_users"].write(
            {
                "user_id": user["id"],
                "email": user["email"],
                "name": user["name"],
                "role": user["role"],
                "company_id": user["company_id"],
                "phone": user["phone"],
                "is_active": _uint(user["is_active"]),
                "email_verified": _uint(user["email_verified"]),
                "phone_verified": _uint(user["phone_verified"]),
                "created_at": user["created_at"],
                "updated_at": user["updated_at"],
                "_deleted": 0,
            }
        )


def _process_warehouses(
    full_dir: Path,
    pg: dict[str, TsvWriter],
    seen: dict[str, set[str]],
    now: str,
) -> None:
    for row in _read_csv(full_dir / "warehouses.csv"):
        warehouse_id = _normalize_uuid(row.get("id"))
        if not warehouse_id or warehouse_id in seen["warehouses"]:
            continue
        city_name = _city_from_row(row)
        city_id = str(uuid.uuid5(CITY_NAMESPACE, city_name.lower()))
        if city_id not in seen["cities"]:
            seen["cities"].add(city_id)
            pg["cities"].write({"id": city_id, "name": city_name, "created_at": now})
        warehouse = {
            "id": warehouse_id,
            "address": _string(row.get("address")) or city_name,
            "brand": _string(row.get("brand")) or "unknown",
            "city_id": city_id,
            "dealer_id": _normalize_uuid(row.get("dealer_id")),
            "company_id": _normalize_uuid(row.get("company_id")),
            "status": _string(row.get("status")) or "active",
            "created_at": _datetime(row.get("created_at")) or now,
            "updated_at": _datetime(row.get("updated_at")) or now,
        }
        seen["warehouses"].add(warehouse_id)
        pg["warehouses"].write(warehouse)


def _process_distributor_links(
    full_dir: Path,
    pg: dict[str, TsvWriter],
    seen: dict[str, set[str]],
    now: str,
) -> None:
    for row in _read_csv(full_dir / "distributor_dealer_links.csv"):
        distributor_id = _normalize_uuid(row.get("distributor_company_id"))
        dealer_id = _normalize_uuid(row.get("dealer_company_id"))
        if not distributor_id or not dealer_id:
            continue
        key = f"{distributor_id}:{dealer_id}"
        if key in seen["links"]:
            continue
        seen["links"].add(key)
        pg["distributor_dealer_links"].write(
            {
                "distributor_company_id": distributor_id,
                "dealer_company_id": dealer_id,
                "created_at": now,
            }
        )


def _process_catalog(
    full_dir: Path,
    catalog_dir: Path,
    pg: dict[str, TsvWriter],
    ch: dict[str, JsonlWriter],
    seen: dict[str, set[str]],
    vehicles_by_id: dict[str, dict[str, Any]],
    manifest: BulkManifest,
    strict: bool,
    now: str,
    image_source_paths: Iterable[Path],
) -> None:
    workbook_paths = sorted(catalog_dir.glob("*.xlsx"))
    explicit_image_sources = list(image_source_paths)
    if (full_dir / "vehicles_master.csv").exists():
        _process_catalog_csv(
            full_dir,
            pg,
            ch,
            seen,
            vehicles_by_id,
            manifest,
            strict,
            now,
            explicit_image_sources or workbook_paths,
        )
        return
    for workbook_path in workbook_paths:
        for line_number, raw in _iter_xlsx_rows(workbook_path):
            parsed = extract_row_data(raw)
            vehicle = dict(parsed["vehicle"])
            vehicle_id = _normalize_uuid(vehicle.get("id"))
            if not vehicle_id:
                _add_anomaly(
                    manifest,
                    strict,
                    {
                        "kind": "catalog_row_without_vehicle_id",
                        "source": str(workbook_path),
                        "row": str(line_number),
                    },
                )
                continue
            if vehicle_id in seen["vehicles"]:
                _add_anomaly(
                    manifest,
                    False,
                    {
                        "kind": "duplicate_vehicle_id",
                        "vehicle_id": vehicle_id,
                        "source": str(workbook_path),
                        "row": str(line_number),
                    },
                )
                continue

            _write_catalog_parts(pg, seen, parsed)
            vehicle["id"] = vehicle_id
            vehicle["dealer_id"] = _normalize_uuid(vehicle.get("dealer_id"))
            vehicle["warehouse_id"] = _normalize_uuid(vehicle.get("warehouse_id"))
            vehicle["images"] = _json(vehicle.get("images") or [])
            vehicle["created_at"] = _datetime(vehicle.get("created_at")) or now
            vehicle["updated_at"] = now
            vehicle["is_available"] = _bool(vehicle.get("is_available"), default=True)
            vehicle["status"] = _string(vehicle.get("status")) or "available"
            vehicle["dealer_cost"] = None
            vehicle["mark_name"] = _string(parsed["mark"].get("name"))
            vehicle["model_name"] = _string(parsed["model"].get("name"))
            seen["vehicles"].add(vehicle_id)
            vehicles_by_id[vehicle_id] = dict(vehicle)
            pg["vehicles"].write(vehicle)
            ch["dwh_vehicles"].write(_dwh_vehicle(vehicle))

            warehouse_id = vehicle.get("warehouse_id")
            if warehouse_id:
                vw_id = str(
                    uuid.uuid5(
                        VEHICLE_WAREHOUSE_NAMESPACE,
                        f"{vehicle_id}:{warehouse_id}",
                    )
                )
                if vw_id not in seen["vehicle_warehouses"]:
                    seen["vehicle_warehouses"].add(vw_id)
                    pg["vehicle_warehouses"].write(
                        {
                            "id": vw_id,
                            "vehicle_id": vehicle_id,
                            "warehouse_id": warehouse_id,
                            "created_at": vehicle["created_at"],
                        }
                    )


def _process_catalog_csv(
    full_dir: Path,
    pg: dict[str, TsvWriter],
    ch: dict[str, JsonlWriter],
    seen: dict[str, set[str]],
    vehicles_by_id: dict[str, dict[str, Any]],
    manifest: BulkManifest,
    strict: bool,
    now: str,
    image_source_paths: Iterable[Path],
) -> None:
    image_pool = _read_excel_image_pool(image_source_paths)
    template_pool = _read_excel_catalog_template_pool(image_source_paths)
    catalog_by_model: dict[str, dict[str, str | None]] = {}
    for row in _read_csv(full_dir / "catalog_mini.csv"):
        mark_name = _string(row.get("mark_name")) or _string(row.get("mark_id"))
        model_name = _string(row.get("model_name")) or _string(row.get("model_id"))
        if not mark_name or not model_name:
            continue
        mark = {
            "id": mark_name,
            "name": mark_name,
            "cyrillic_name": None,
            "popular": 0,
            "country": None,
        }
        model = {
            "id": model_name,
            "name": model_name,
            "cyrillic_name": None,
            "class": None,
            "year_from": None,
            "year_to": None,
            "mark_id": mark_name,
        }
        _write_unique(pg["mark"], seen["mark"], mark, "id")
        _write_unique(pg["model"], seen["model"], model, "id")
        catalog_by_model[model_name] = {
            "mark_id": mark_name,
            "mark_name": mark_name,
            "model_id": model_name,
            "model_name": model_name,
        }

    for row in _read_csv(full_dir / "vehicles_master.csv"):
        vehicle_id = _normalize_uuid(row.get("id"))
        if not vehicle_id:
            _add_anomaly(manifest, strict, {"kind": "csv_vehicle_without_id"})
            continue
        if vehicle_id in seen["vehicles"]:
            _add_anomaly(
                manifest,
                False,
                {"kind": "duplicate_vehicle_id", "vehicle_id": vehicle_id},
            )
            continue
        model_id = _string(row.get("model_id"))
        mark_id = _string(row.get("mark_id"))
        catalog_ref = catalog_by_model.get(model_id or "") or {}
        mark_name = _string(catalog_ref.get("mark_name")) or mark_id
        model_name = _string(catalog_ref.get("model_name")) or model_id
        catalog_template = _catalog_template_or_synthetic(
            template_pool,
            mark_name=mark_name,
            model_name=model_name,
            vehicle_id=vehicle_id,
        )
        _write_catalog_parts(pg, seen, catalog_template)
        vehicle = {
            "id": vehicle_id,
            "vin": _string(row.get("vin")),
            "dealer_id": _normalize_uuid(row.get("dealer_id")),
            "warehouse_id": _normalize_uuid(row.get("warehouse_id")),
            "mark_id": _string(catalog_ref.get("mark_id")) or mark_id,
            "model_id": _string(catalog_ref.get("model_id")) or model_id,
            "generation_id": _string(catalog_template["generation"].get("id")),
            "configuration_id": _string(catalog_template["configuration"].get("id")),
            "complectation_id": _string(
                catalog_template["modification"].get("complectation_id")
            ),
            "year": _int(row.get("year")),
            "base_price": _capped_decimal(row.get("base_price")),
            "special_price": _capped_decimal(row.get("special_price")),
            "dealer_cost": None,
            "discount_price": _capped_decimal(row.get("special_price")),
            "color": _string(row.get("color")),
            "color_inter": _string(row.get("color_inter")),
            "images": _json(
                image_pool.images_for(
                    mark_name=mark_name,
                    model_name=model_name,
                    vehicle_id=vehicle_id,
                )
            ),
            "status": _string(row.get("status")) or "available",
            "is_available": _bool(row.get("is_available"), default=True),
            "created_at": _datetime(row.get("created_at")) or now,
            "updated_at": now,
            "mark_name": mark_name,
            "model_name": model_name,
        }
        seen["vehicles"].add(vehicle_id)
        vehicles_by_id[vehicle_id] = dict(vehicle)
        pg["vehicles"].write(vehicle)
        ch["dwh_vehicles"].write(_dwh_vehicle(vehicle))

        warehouse_id = vehicle.get("warehouse_id")
        if warehouse_id:
            vw_id = str(
                uuid.uuid5(VEHICLE_WAREHOUSE_NAMESPACE, f"{vehicle_id}:{warehouse_id}")
            )
            if vw_id not in seen["vehicle_warehouses"]:
                seen["vehicle_warehouses"].add(vw_id)
                pg["vehicle_warehouses"].write(
                    {
                        "id": vw_id,
                        "vehicle_id": vehicle_id,
                        "warehouse_id": warehouse_id,
                        "created_at": vehicle["created_at"],
                    }
                )


def _read_excel_image_pool(paths: Iterable[Path]) -> ExcelImagePool:
    by_mark_model: dict[tuple[str, str], list[str]] = {}
    by_mark: dict[str, list[str]] = {}
    all_images: list[str] = []
    seen_global: set[str] = set()

    for path in paths:
        if not path.exists() or path.suffix.lower() != ".xlsx":
            continue
        for _line_number, row in _iter_xlsx_rows(path):
            parsed = extract_row_data(row)
            images = [*parsed["image_filenames"], *parsed["image_urls"]]
            if not images:
                continue
            mark_name = _image_key(parsed["mark"].get("name") or row.get("Марка"))
            model_name = _image_key(parsed["model"].get("name") or row.get("Модель"))
            if not mark_name:
                continue
            for image in images:
                if image not in seen_global:
                    seen_global.add(image)
                    all_images.append(image)
                if model_name:
                    _append_unique(by_mark_model.setdefault((mark_name, model_name), []), image)
                _append_unique(by_mark.setdefault(mark_name, []), image)

    return ExcelImagePool(
        by_mark_model=by_mark_model,
        by_mark=by_mark,
        all_images=all_images,
    )


def _read_excel_catalog_template_pool(paths: Iterable[Path]) -> ExcelCatalogTemplatePool:
    by_mark_model: dict[tuple[str, str], list[ParsedRow]] = {}
    by_mark: dict[str, list[ParsedRow]] = {}
    all_templates: list[ParsedRow] = []
    seen_templates: set[str] = set()

    for path in paths:
        if not path.exists() or path.suffix.lower() != ".xlsx":
            continue
        for _line_number, row in _iter_xlsx_rows(path):
            parsed = extract_row_data(row)
            mark_name = _image_key(parsed["mark"].get("name") or row.get("Марка"))
            model_name = _image_key(parsed["model"].get("name") or row.get("Модель"))
            complectation_id = _string(
                parsed["modification"].get("complectation_id")
            )
            configuration_id = _string(parsed["configuration"].get("id"))
            if (
                not mark_name
                or not model_name
                or not complectation_id
                or not configuration_id
                or not parsed.get("has_specifications")
            ):
                continue
            template_key = f"{mark_name}:{model_name}:{complectation_id}"
            if template_key in seen_templates:
                continue
            seen_templates.add(template_key)
            all_templates.append(parsed)
            by_mark_model.setdefault((mark_name, model_name), []).append(parsed)
            by_mark.setdefault(mark_name, []).append(parsed)

    return ExcelCatalogTemplatePool(
        by_mark_model=by_mark_model,
        by_mark=by_mark,
        all_templates=all_templates,
    )


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _image_key(value: Any) -> str:
    return (_string(value) or "").casefold()


def _stable_index(seed: str, size: int) -> int:
    digest = hashlib.blake2b(seed.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") % size


def _catalog_template_or_synthetic(
    template_pool: ExcelCatalogTemplatePool,
    *,
    mark_name: str | None,
    model_name: str | None,
    vehicle_id: str,
) -> dict[str, Any]:
    template = template_pool.template_for(
        mark_name=mark_name,
        model_name=model_name,
        vehicle_id=vehicle_id,
    )
    synthetic = _synthetic_catalog_template(
        mark_name=mark_name,
        model_name=model_name,
        vehicle_id=vehicle_id,
    )
    if template:
        return _catalog_template_with_core_fallbacks(template, synthetic)
    return synthetic


def _catalog_template_with_core_fallbacks(
    template: Mapping[str, Any],
    fallback: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(template)
    result["configuration"] = dict(template["configuration"])
    result["specifications"] = dict(template["specifications"])
    if not _string(result["configuration"].get("body_type")):
        result["configuration"]["body_type"] = fallback["configuration"]["body_type"]
    for column in ("engine_type", "horse_power", "drive", "volume", "transmission"):
        if not _string(result["specifications"].get(column)):
            result["specifications"][column] = fallback["specifications"][column]
    return result


def _synthetic_catalog_template(
    *,
    mark_name: str | None,
    model_name: str | None,
    vehicle_id: str,
) -> dict[str, Any]:
    mark = _string(mark_name) or "Unknown"
    model = _string(model_name) or "Model"
    base = f"{mark}.{model}.{vehicle_id}"
    generation_id = str(uuid.uuid5(REFERENCE_NAMESPACE, f"synthetic.generation.{base}"))
    configuration_id = str(uuid.uuid5(REFERENCE_NAMESPACE, f"synthetic.config.{base}"))
    complectation_id = str(uuid.uuid5(REFERENCE_NAMESPACE, f"synthetic.mod.{base}"))
    digest = _stable_index(base, 10_000)
    body_by_model = {
        "Vesta": "SEDAN",
        "Granta": "SEDAN",
        "Largus": "WAGON_5_DOORS",
        "Niva": "SUV_5_DOORS",
        "Solaris": "SEDAN",
        "C5 GT": "SUV_5_DOORS",
    }
    drive_values = ["Передний", "Передний", "Полный"]
    volume_values = ["1.5", "1.6", "2.0"]
    transmission_values = ["AUTOMATIC", "ROBOT", "VARIATOR"]
    specs = dict.fromkeys(SPECIFICATION_COLUMNS)
    specs.update(
        {
            "engine_type": "Бензиновый",
            "horse_power": str(106 + (digest % 144)),
            "drive": drive_values[digest % len(drive_values)],
            "volume": volume_values[digest % len(volume_values)],
            "volume_litres": str(int(float(volume_values[digest % len(volume_values)]) * 1000)),
            "transmission": transmission_values[digest % len(transmission_values)],
        }
    )
    return {
        "mark": {
            "id": mark,
            "name": mark,
            "cyrillic_name": None,
            "popular": 0,
            "country": None,
        },
        "model": {
            "id": model,
            "name": model,
            "cyrillic_name": None,
            "class": None,
            "year_from": None,
            "year_to": None,
            "mark_id": mark,
        },
        "generation": {
            "id": generation_id,
            "name": "I",
            "year_start": None,
            "year_stop": None,
            "is_restyle": 0,
            "model_id": model,
        },
        "configuration": {
            "id": configuration_id,
            "doors_count": 5,
            "body_type": body_by_model.get(model, "SUV_5_DOORS"),
            "configuration_name": "Base",
            "generation_id": generation_id,
        },
        "modification": {
            "complectation_id": complectation_id,
            "offers_price_from": None,
            "offers_price_to": None,
            "group_name": "Base",
            "configuration_id": configuration_id,
        },
        "options": dict.fromkeys(OPTION_COLUMNS),
        "specifications": specs,
        "has_options": False,
        "has_specifications": True,
    }


def _write_catalog_parts(
    pg: dict[str, TsvWriter],
    seen: dict[str, set[str]],
    parsed: Mapping[str, Any],
) -> None:
    _write_unique(pg["mark"], seen["mark"], parsed["mark"], "id")
    _write_unique(pg["model"], seen["model"], parsed["model"], "id")
    _write_unique(pg["generation"], seen["generation"], parsed["generation"], "id")
    _write_unique(
        pg["configuration"], seen["configuration"], parsed["configuration"], "id"
    )
    _write_unique(
        pg["modification"],
        seen["modification"],
        parsed["modification"],
        "complectation_id",
    )
    if parsed.get("has_options"):
        _write_unique(
            pg["options"],
            seen["options"],
            {"complectation_id": parsed["modification"]["complectation_id"], **parsed["options"]},
            "complectation_id",
        )
    if parsed.get("has_specifications"):
        _write_unique(
            pg["specifications"],
            seen["specifications"],
            {
                "complectation_id": parsed["modification"]["complectation_id"],
                **parsed["specifications"],
            },
            "complectation_id",
        )


def _write_unique(
    writer: TsvWriter,
    seen: set[str],
    row: Mapping[str, Any],
    id_column: str,
) -> None:
    key = _string(row.get(id_column))
    if not key or key in seen:
        return
    seen.add(key)
    writer.write(row)


def _process_lca(
    full_dir: Path,
    pg: dict[str, TsvWriter],
    ch: dict[str, JsonlWriter],
    seen: dict[str, set[str]],
    vehicles_by_id: dict[str, dict[str, Any]],
    companies_by_id: dict[str, dict[str, Any]],
    applications: dict[str, dict[str, Any]],
    application_lcs: dict[str, set[str]],
    display_counters: dict[tuple[str, str], int],
    leasing_company_ids: set[str],
    manifest: BulkManifest,
    strict: bool,
    now: str,
) -> None:
    for row in _read_csv(full_dir / "lca.csv"):
        lca_id = _normalize_uuid(row.get("id")) or str(uuid.uuid4())
        application_id = _normalize_uuid(row.get("application_id"))
        if not application_id:
            _add_anomaly(manifest, strict, {"kind": "lca_without_application_id", "lca_id": lca_id})
            continue
        leasing_company_id = _normalize_uuid(row.get("leasing_company_id"))
        if leasing_company_id:
            leasing_company_ids.add(leasing_company_id)
            application_lcs.setdefault(application_id, set()).add(leasing_company_id)
        manifest.application_ids.add(application_id)

        vehicle_id = _normalize_uuid(row.get("vehicle_id"))
        vehicle = vehicles_by_id.get(vehicle_id or "")
        created_at = _datetime(row.get("created_at")) or now
        app = applications.setdefault(
            application_id,
            _application_from_lca_row(
                row,
                application_id,
                vehicle_id,
                companies_by_id,
                display_counters,
                created_at,
                now,
            ),
        )
        _merge_application(app, row, vehicle_id, created_at, now)

        lca = {
            "id": lca_id,
            "application_id": application_id,
            "leasing_company_id": leasing_company_id,
            "status": _lca_status(row.get("status")),
            "submitted_at": _submitted_at(row, created_at, lca_id, application_id),
            "created_at": created_at,
            "updated_at": _datetime(row.get("updated_at")) or now,
        }
        pg["leasing_company_applications"].write(lca)
        ch["dwh_leasing_company_applications"].write(
            _dwh_lca(
                lca,
                app,
                vehicle,
                [leasing_company_id] if leasing_company_id else [],
                companies_by_id,
            )
        )

        if vehicle_id and vehicle_id not in vehicles_by_id:
            _add_anomaly(
                manifest,
                strict,
                {
                    "kind": "missing_lca_vehicle",
                    "vehicle_id": vehicle_id,
                    "application_id": application_id,
                },
            )
            continue
        if not vehicle_id:
            continue

        app_vehicle_id = str(
            uuid.uuid5(APPLICATION_VEHICLE_NAMESPACE, f"{application_id}:{vehicle_id}")
        )
        if app_vehicle_id in seen["application_vehicles"]:
            continue
        seen["application_vehicles"].add(app_vehicle_id)
        app_vehicle = {
            "id": app_vehicle_id,
            "application_id": application_id,
            "vehicle_id": vehicle_id,
            "modification_id": _string(row.get("modification_id"))
            or _string(vehicle.get("complectation_id") if vehicle else None),
            "quantity": _int(row.get("quantity")) or 1,
            "unit_price": _decimal(row.get("unit_price"))
            or _decimal(vehicle.get("discount_price") if vehicle else None)
            or _decimal(vehicle.get("special_price") if vehicle else None)
            or _decimal(vehicle.get("base_price") if vehicle else None),
            "total_price": _decimal(row.get("total_price"))
            or _decimal(row.get("unit_price"))
            or _decimal(app.get("total_amount")),
            "vin": _string(vehicle.get("vin") if vehicle else row.get("vin")),
            "is_model_order": False,
            "created_at": created_at,
            "updated_at": now,
        }
        pg["application_vehicles"].write(app_vehicle)
        ch["dwh_application_vehicles"].write(_dwh_application_vehicle(app_vehicle))


def _application_from_lca_row(
    row: Mapping[str, Any],
    application_id: str,
    vehicle_id: str | None,
    companies_by_id: Mapping[str, Mapping[str, Any]],
    display_counters: dict[tuple[str, str], int],
    created_at: str,
    now: str,
) -> dict[str, Any]:
    return {
        "id": application_id,
        "display_number": _display_number(row, companies_by_id, display_counters),
        "company_id": _normalize_uuid(row.get("company_id")),
        "dealer_company_id": _normalize_uuid(row.get("dealer_company_id")),
        "vehicle_id": vehicle_id,
        "name": _string(row.get("name")),
        "email": _string(row.get("email")),
        "status": _application_status(
            row.get("application_status") or _parent_status_from_lca(row.get("status"))
        ),
        "total_amount": _decimal(row.get("total_amount")),
        "down_payment": _decimal(row.get("down_payment")),
        "down_payment_percent": _decimal(row.get("down_payment_percent")),
        "lease_term_months": _int(row.get("lease_term_months")),
        "monthly_payment": _decimal(row.get("monthly_payment")),
        "total_cost": _decimal(row.get("total_cost")),
        "markup": _decimal(row.get("markup")),
        "rate": _decimal(row.get("rate")),
        "selected_leasing_companies": None,
        "questionnaire_completed": False,
        "questionnaire_progress": 0,
        "current_stage": _string(row.get("current_stage")) or "leasing_companies",
        "created_at": created_at,
        "updated_at": _datetime(row.get("updated_at")) or now,
    }


def _merge_application(
    app: dict[str, Any],
    row: Mapping[str, Any],
    vehicle_id: str | None,
    created_at: str,
    now: str,
) -> None:
    for column in (
        "display_number",
        "company_id",
        "dealer_company_id",
        "name",
        "email",
        "total_amount",
        "down_payment",
        "down_payment_percent",
        "lease_term_months",
        "monthly_payment",
        "total_cost",
        "markup",
        "rate",
    ):
        if app.get(column) is None:
            candidate = _decimal(row.get(column)) if column in _MONEY_COLUMNS else row.get(column)
            app[column] = _normalize_uuid(candidate) if column.endswith("_id") else _string(candidate)
    if app.get("vehicle_id") is None and vehicle_id:
        app["vehicle_id"] = vehicle_id
    if created_at < app.get("created_at", created_at):
        app["created_at"] = created_at
    app["updated_at"] = _datetime(row.get("updated_at")) or now


_MONEY_COLUMNS = {
    "total_amount",
    "down_payment",
    "down_payment_percent",
    "monthly_payment",
    "total_cost",
    "markup",
    "rate",
}


def _display_number(
    row: Mapping[str, Any],
    companies_by_id: Mapping[str, Mapping[str, Any]],
    counters: dict[tuple[str, str], int],
) -> str | None:
    company_id = _normalize_uuid(row.get("company_id"))
    company = companies_by_id.get(company_id or "", {})
    inn = _string(company.get("inn")) or _synthetic_inn(company_id)
    created_at = _datetime(row.get("created_at"))
    if not inn or not created_at:
        return _string(row.get("display_number"))
    parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    mmdd = parsed.strftime("%m%d")
    key = (inn, mmdd)
    counters[key] = counters.get(key, 0) + 1
    return f"{inn}-{mmdd}-{counters[key]:03d}"


def _synthetic_inn(seed: str | None) -> str | None:
    if not seed:
        return None
    digest = hashlib.blake2b(seed.encode(), digest_size=8).digest()
    number = int.from_bytes(digest, "big") % 10_000_000_000
    return f"{number:010d}"


def _write_leasing_companies(
    pg: dict[str, TsvWriter],
    seen: dict[str, set[str]],
    leasing_company_ids: set[str],
    companies_by_id: Mapping[str, Mapping[str, Any]],
    now: str,
) -> None:
    leasing_company_rows: list[dict[str, Any]] = [
        {
            "id": company["id"],
            "company_id": company["id"],
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        for company in companies_by_id.values()
        if company.get("company_type") == "leasing_company"
    ]
    leasing_company_rows.extend(
        [
            {
                "id": leasing_company_id,
                "company_id": leasing_company_id
                if leasing_company_id in companies_by_id
                else None,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            for leasing_company_id in sorted(leasing_company_ids)
        ]
    )
    for row in leasing_company_rows:
        row_id = row["id"]
        if row_id in seen["leasing_companies"]:
            continue
        seen["leasing_companies"].add(row_id)
        pg["leasing_companies"].write(row)


def _write_leasing_applications(
    pg: dict[str, TsvWriter],
    applications: Mapping[str, dict[str, Any]],
    application_lcs: Mapping[str, set[str]],
) -> None:
    for application_id in sorted(applications):
        row = dict(applications[application_id])
        selected = sorted(application_lcs.get(application_id, set()))
        row["selected_leasing_companies"] = _pg_uuid_array(selected) if selected else None
        pg["leasing_applications"].write(row)


def _process_exchange_requests(
    full_dir: Path,
    pg: dict[str, TsvWriter],
    ch: dict[str, JsonlWriter],
    seen: dict[str, set[str]],
    vehicles_by_id: Mapping[str, Mapping[str, Any]],
    manifest: BulkManifest,
    strict: bool,
    now: str,
) -> None:
    for row in _read_csv(full_dir / "exchange_requests.csv"):
        request_id = _normalize_uuid(row.get("id"))
        vehicle_id = _normalize_uuid(row.get("vehicle_id"))
        if not request_id or request_id in seen["exchange_requests"]:
            continue
        if vehicle_id and vehicle_id not in vehicles_by_id:
            _add_anomaly(
                manifest,
                strict,
                {
                    "kind": "missing_exchange_request_vehicle",
                    "request_id": request_id,
                    "vehicle_id": vehicle_id,
                },
            )
            continue
        request = {
            "id": request_id,
            "lc_user_id": _normalize_uuid(row.get("lc_user_id")),
            "vehicle_id": vehicle_id,
            "distributor_id": _normalize_uuid(row.get("distributor_id")),
            "quantity": _int(row.get("quantity")) or 1,
            "expiration_date": _date(row.get("expiration_date")),
            "discount_type": _string(row.get("discount_type")),
            "discount_value": _decimal(row.get("discount_value")),
            "file_url": _string(row.get("file_url")),
            "file_name": _string(row.get("file_name")),
            "status": _string(row.get("status")) or "open",
            "accepted_bid_id": _normalize_uuid(row.get("accepted_bid_id")),
            "batch_number": _int(row.get("batch_number")),
            "batch_index": _int(row.get("batch_index")),
            "created_at": _datetime(row.get("created_at")) or now,
            "updated_at": _datetime(row.get("updated_at")) or now,
        }
        seen["exchange_requests"].add(request_id)
        pg["exchange_requests"].write(request)
        ch["dwh_exchange_requests"].write(_dwh_exchange_request(request))


def _process_exchange_bids(
    full_dir: Path,
    pg: dict[str, TsvWriter],
    ch: dict[str, JsonlWriter],
    seen: dict[str, set[str]],
    manifest: BulkManifest,
    now: str,
) -> None:
    for row in _read_csv(full_dir / "exchange_bids.csv"):
        bid_id = _normalize_uuid(row.get("id"))
        request_id = _normalize_uuid(row.get("request_id"))
        dealer_id = _normalize_uuid(row.get("dealer_id"))
        if not bid_id or bid_id in seen["exchange_bids"]:
            continue
        if not request_id or not dealer_id:
            _add_anomaly(
                manifest,
                False,
                {"kind": "exchange_bid_without_required_fk", "bid_id": bid_id},
            )
            continue
        bid = {
            "id": bid_id,
            "request_id": request_id,
            "dealer_id": dealer_id,
            "distributor_id": _normalize_uuid(row.get("distributor_id")),
            "price": _decimal(row.get("price")) or Decimal("0"),
            "comment": _string(row.get("comment")),
            "is_accepted": _bool(row.get("is_accepted"), default=False),
            "kp_file_url": _string(row.get("kp_file_url")),
            "kp_file_name": _string(row.get("kp_file_name")),
            "kp_status": _string(row.get("kp_status")) or "none",
            "kp_dealer_comment": _string(row.get("kp_dealer_comment")),
            "kp_sent_at": _datetime(row.get("kp_sent_at")),
            "kp_responded_at": _datetime(row.get("kp_responded_at")),
            "quantity": _int(row.get("quantity")) or 1,
            "bid_file_url": _string(row.get("bid_file_url")),
            "bid_file_name": _string(row.get("bid_file_name")),
            "created_at": _datetime(row.get("created_at")) or now,
            "updated_at": _datetime(row.get("updated_at")) or now,
        }
        seen["exchange_bids"].add(bid_id)
        pg["exchange_bids"].write(bid)
        ch["dwh_exchange_bids"].write(_dwh_exchange_bid(bid))


def _dwh_company(company: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "company_id": company["id"],
        "name": company["name"],
        "inn": company["inn"],
        "kpp": company["kpp"],
        "ogrn": company["ogrn"],
        "company_type": company["company_type"],
        "address": company["address"],
        "contact_info": company["contact_info"],
        "legal_address": company["legal_address"],
        "actual_address": company["actual_address"],
        "phone": company["phone"],
        "email": company["email"],
        "website": company["website"],
        "is_active": _uint(company["is_active"]),
        "full_name": company["full_name"],
        "short_name": company["short_name"],
        "okpo": company["okpo"],
        "okato": company["okato"],
        "legal_form": company["legal_form"],
        "region": company["region"],
        "city": company["city"],
        "registration_date": company["registration_date"],
        "employees_count": company["employees_count"],
        "main_okved_code": company["main_okved_code"],
        "main_okved_description": company["main_okved_description"],
        "director_full_name": company["director_full_name"],
        "bank_bik": company["bank_bik"],
        "bank_name": company["bank_name"],
        "authorized_capital": company["authorized_capital"],
        "net_profit": company["net_profit"],
        "reporting_year": company["reporting_year"],
        "tax_system": company["tax_system"],
        "enrichment_status": company["enrichment_status"],
        "created_at": company["created_at"],
        "updated_at": company["updated_at"],
        "_deleted": 0,
    }


def _dwh_vehicle(vehicle: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "vehicle_id": vehicle["id"],
        "vin": vehicle.get("vin"),
        "dealer_id": vehicle.get("dealer_id"),
        "mark_id": vehicle.get("mark_id"),
        "model_id": vehicle.get("model_id"),
        "generation_id": vehicle.get("generation_id"),
        "configuration_id": vehicle.get("configuration_id"),
        "complectation_id": vehicle.get("complectation_id"),
        "year": vehicle.get("year"),
        "base_price": vehicle.get("base_price"),
        "special_price": vehicle.get("special_price"),
        "dealer_cost": vehicle.get("dealer_cost"),
        "discount_price": vehicle.get("discount_price"),
        "color": vehicle.get("color"),
        "color_inter": vehicle.get("color_inter"),
        "images": vehicle.get("images"),
        "status": vehicle.get("status"),
        "is_available": _uint(vehicle.get("is_available")),
        "created_at": vehicle.get("created_at"),
        "updated_at": vehicle.get("updated_at"),
        "_deleted": 0,
    }


def _dwh_lca(
    lca: Mapping[str, Any],
    app: Mapping[str, Any],
    vehicle: Mapping[str, Any] | None,
    selected_lcs: list[str],
    companies_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    leasing_company = companies_by_id.get(str(lca.get("leasing_company_id")) or "", {})
    dealer = companies_by_id.get(str(app.get("dealer_company_id")) or "", {})
    return {
        "lca_id": lca["id"],
        "application_id": lca["application_id"],
        "leasing_company_id": lca["leasing_company_id"],
        "dealer_id": app.get("dealer_company_id"),
        "dealer_company_id": app.get("dealer_company_id"),
        "client_company_id": app.get("company_id"),
        "distributor_id": None,
        "display_number": app.get("display_number"),
        "vehicle_id": app.get("vehicle_id"),
        "name": app.get("name"),
        "email": app.get("email"),
        "application_status": app.get("status"),
        "total_amount": app.get("total_amount"),
        "down_payment": app.get("down_payment"),
        "down_payment_percent": app.get("down_payment_percent"),
        "lease_term_months": app.get("lease_term_months"),
        "monthly_payment": app.get("monthly_payment"),
        "total_cost": app.get("total_cost"),
        "markup": app.get("markup"),
        "rate": app.get("rate"),
        "selected_leasing_companies": _json(selected_lcs),
        "questionnaire_completed": _uint(app.get("questionnaire_completed")),
        "questionnaire_progress": app.get("questionnaire_progress"),
        "current_stage": app.get("current_stage"),
        "status": lca.get("status"),
        "submitted_at": lca.get("submitted_at"),
        "vehicle_mark_id": vehicle.get("mark_id") if vehicle else None,
        "vehicle_model_id": vehicle.get("model_id") if vehicle else None,
        "dealer_name": dealer.get("name"),
        "dealer_city": dealer.get("city"),
        "mark_name": vehicle.get("mark_name") if vehicle else None,
        "model_name": vehicle.get("model_name") if vehicle else None,
        "leasing_company_name": leasing_company.get("name"),
        "created_at": lca.get("created_at"),
        "updated_at": lca.get("updated_at"),
        "_deleted": 0,
    }


def _dwh_application_vehicle(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "application_id": row["application_id"],
        "vehicle_id": row["vehicle_id"],
        "modification_id": row["modification_id"],
        "quantity": row["quantity"],
        "unit_price": row["unit_price"],
        "total_price": row["total_price"],
        "comment": None,
        "vin": row["vin"],
        "is_model_order": _uint(row["is_model_order"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "_deleted": 0,
    }


def _dwh_exchange_request(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "request_id": row["id"],
        "lc_user_id": row["lc_user_id"],
        "vehicle_id": row["vehicle_id"],
        "quantity": row["quantity"],
        "expiration_date": row["expiration_date"],
        "discount_type": row["discount_type"],
        "discount_value": row["discount_value"],
        "file_url": row["file_url"],
        "file_name": row["file_name"],
        "status": row["status"],
        "accepted_bid_id": row["accepted_bid_id"],
        "batch_number": row["batch_number"],
        "batch_index": row["batch_index"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "_deleted": 0,
    }


def _dwh_exchange_bid(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "bid_id": row["id"],
        "request_id": row["request_id"],
        "dealer_id": row["dealer_id"],
        "price": row["price"],
        "comment": row["comment"],
        "is_accepted": _uint(row["is_accepted"]),
        "kp_file_url": row["kp_file_url"],
        "kp_file_name": row["kp_file_name"],
        "kp_status": row["kp_status"],
        "kp_dealer_comment": row["kp_dealer_comment"],
        "kp_sent_at": row["kp_sent_at"],
        "kp_responded_at": row["kp_responded_at"],
        "quantity": row["quantity"],
        "bid_file_url": row["bid_file_url"],
        "bid_file_name": row["bid_file_name"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "_deleted": 0,
    }


def _reference_uuid(seed: str) -> str:
    return str(uuid.uuid5(REFERENCE_NAMESPACE, seed))


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float | Decimal):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _sql_text_array(values: Iterable[str]) -> str:
    items = ", ".join(_sql_literal(value) for value in values)
    return f"ARRAY[{items}]::text[]"


def _reference_leasing_rates_sql() -> str:
    return f"""
INSERT INTO leasing_rates (id, date_from, date_to, key_rate, surcharge, vat_rate, profit_tax_rate)
SELECT '{_reference_uuid("leasing_rate.default")}'::uuid, CURRENT_DATE, NULL, 15, 6, 20, 25
WHERE NOT EXISTS (
    SELECT 1
    FROM leasing_rates
    WHERE date_to IS NULL
);
""".strip()


def _reference_document_types_sql() -> str:
    rows = [
        "("
        + ", ".join(
            [
                _sql_literal(_reference_uuid(f"document_type.{item['type_code']}")) + "::uuid",
                _sql_literal(item["name"]),
                _sql_literal(item["type_code"]),
                _sql_literal(item["display_name"]),
                _sql_literal(item["description"]),
                _sql_text_array(item["file_types"]),
                _sql_literal(item["max_file_size_mb"]),
                _sql_literal(item["auto_approve"]),
            ]
        )
        + ")"
        for item in REFERENCE_DOCUMENT_TYPES
    ]
    return f"""
INSERT INTO document_types (
    id, name, type_code, display_name, description, file_types,
    max_file_size_mb, auto_approve
)
VALUES
    {",\n    ".join(rows)}
ON CONFLICT (type_code) DO UPDATE SET
    name = EXCLUDED.name,
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    file_types = EXCLUDED.file_types,
    max_file_size_mb = EXCLUDED.max_file_size_mb,
    auto_approve = EXCLUDED.auto_approve,
    updated_at = CURRENT_TIMESTAMP;
""".strip()


def _reference_dealer_options_sql() -> str:
    rows = []
    for index, name in enumerate(REFERENCE_DEALER_OPTIONS, start=1):
        rows.append(
            "("
            + ", ".join(
                [
                    _sql_literal(_reference_uuid(f"dealer_option.{name}")) + "::uuid",
                    _sql_literal(name),
                    str(index),
                    "TRUE",
                ]
            )
            + ")"
        )
    return f"""
INSERT INTO dealer_options (id, name, sort_order, is_active)
VALUES
    {",\n    ".join(rows)}
ON CONFLICT ON CONSTRAINT dealer_options_name_unique DO UPDATE SET
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    updated_at = CURRENT_TIMESTAMP;
""".strip()


def _reference_cities_sql() -> str:
    rows = ",\n    ".join(
        f"({_sql_literal(_reference_uuid(f'city.{name}'))}::uuid, {_sql_literal(name)})"
        for name in REFERENCE_CITIES
    )
    return f"""
WITH seed(id, name) AS (
    VALUES
    {rows}
)
INSERT INTO cities (id, name)
SELECT seed.id, seed.name
FROM seed
WHERE NOT EXISTS (
    SELECT 1 FROM cities WHERE cities.name = seed.name
);
""".strip()


def _reference_report_types_sql() -> str:
    rows = ",\n    ".join(
        "("
        + ", ".join(
            [
                _sql_literal(knd),
                _sql_literal(okud),
                _sql_literal(name),
                _sql_literal(description),
                "TRUE",
            ]
        )
        + ")"
        for knd, okud, name, description in REFERENCE_REPORT_TYPES
    )
    return f"""
INSERT INTO report_types (knd, okud, name, description, is_active)
VALUES
    {rows}
ON CONFLICT (knd) DO UPDATE SET
    okud = EXCLUDED.okud,
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_active = EXCLUDED.is_active;
""".strip()


def _reference_report_codes_sql() -> str:
    rows = ",\n    ".join(
        "("
        + ", ".join(
            [
                _sql_literal(_reference_uuid(f"report_code.{okud}.{code}.{xml_tag}")) + "::uuid",
                _sql_literal(okud),
                _sql_literal(code),
                _sql_literal(xml_tag),
                _sql_literal(name),
                "TRUE",
            ]
        )
        + ")"
        for okud, code, xml_tag, name in REFERENCE_REPORT_CODES
    )
    return f"""
WITH seed(id, okud, code, xml_tag, name, is_active) AS (
    VALUES
    {rows}
)
INSERT INTO report_codes (id, okud, code, xml_tag, name, is_active)
SELECT seed.id, seed.okud, seed.code, seed.xml_tag, seed.name, seed.is_active
FROM seed
WHERE NOT EXISTS (
    SELECT 1
    FROM report_codes
    WHERE report_codes.okud = seed.okud
      AND report_codes.code = seed.code
      AND report_codes.xml_tag IS NOT DISTINCT FROM seed.xml_tag
);
""".strip()


def _reference_nds_tax_rates_sql() -> str:
    rows = ",\n    ".join(
        "("
        + ", ".join(
            [
                _sql_literal(_reference_uuid(f"nds_tax_rate.{xml_tag}")) + "::uuid",
                _sql_literal(xml_tag),
                _sql_literal(tax_base_description),
                _sql_literal(tax_amount_description),
                "TRUE",
            ]
        )
        + ")"
        for xml_tag, tax_base_description, tax_amount_description in REFERENCE_NDS_TAX_RATES
    )
    return f"""
WITH seed(id, xml_tag, tax_base_description, tax_amount_description, is_active) AS (
    VALUES
    {rows}
)
INSERT INTO nds_tax_rates (
    id, xml_tag, tax_base_description, tax_amount_description, is_active
)
SELECT
    seed.id, seed.xml_tag, seed.tax_base_description,
    seed.tax_amount_description, seed.is_active
FROM seed
WHERE NOT EXISTS (
    SELECT 1
    FROM nds_tax_rates
    WHERE nds_tax_rates.xml_tag = seed.xml_tag
);
""".strip()


def _reference_lc_document_requirements_function_sql() -> str:
    return """
CREATE OR REPLACE FUNCTION pg_temp.refresh_seed_leasing_company_document_requirements()
RETURNS void
LANGUAGE sql
AS $$
    INSERT INTO leasing_company_document_requirements (
        id, leasing_company_id, document_type_id, is_required, is_active, sort_order
    )
    SELECT
        (
            substr(seed_hash.hash, 1, 8) || '-' ||
            substr(seed_hash.hash, 9, 4) || '-' ||
            substr(seed_hash.hash, 13, 4) || '-' ||
            substr(seed_hash.hash, 17, 4) || '-' ||
            substr(seed_hash.hash, 21, 12)
        )::uuid,
        lc.id,
        dt.id,
        TRUE,
        TRUE,
        CASE dt.type_code
            WHEN 'accounting_report_xml' THEN 10
            WHEN 'profit_tax_declaration_xml' THEN 11
            WHEN 'vat_declaration_xml' THEN 12
            WHEN 'usn_declaration_xml' THEN 13
            ELSE 100
        END
    FROM leasing_companies lc
    CROSS JOIN document_types dt
    CROSS JOIN LATERAL (
        SELECT md5('lc_doc_req:' || lc.id::text || ':' || dt.type_code) AS hash
    ) seed_hash
    WHERE lc.is_active = TRUE
      AND dt.type_code IN (
          'accounting_report_xml',
          'profit_tax_declaration_xml',
          'vat_declaration_xml',
          'usn_declaration_xml'
      )
    ON CONFLICT (leasing_company_id, document_type_id) DO UPDATE SET
        is_active = TRUE,
        is_required = TRUE,
        sort_order = EXCLUDED.sort_order,
        updated_at = CURRENT_TIMESTAMP;
$$;
""".strip()


def _write_postgres_reference_seed_sql(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    statements = [
        "-- System reference seed for full import bundles. No demo business rows.",
        _reference_leasing_rates_sql(),
        _reference_document_types_sql(),
        _reference_dealer_options_sql(),
        _reference_cities_sql(),
        _reference_report_types_sql(),
        _reference_report_codes_sql(),
        _reference_nds_tax_rates_sql(),
        _reference_lc_document_requirements_function_sql(),
        "",
    ]
    path.write_text("\n\n".join(statements), encoding="utf-8")


def _write_postgres_sql(path: Path, data_dir: Path, reference_seed_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    statements = [
        "\\set ON_ERROR_STOP on",
        "BEGIN;",
        "SET LOCAL synchronous_commit = off;",
        "CREATE EXTENSION IF NOT EXISTS pgcrypto;",
        _full_import_cleanup_sql(),
        *_table_sql("cities", CITY_COLUMNS, data_dir, _upsert_cities()),
        f"\\ir {_sql_path(reference_seed_path)}",
        *_stage_and_upsert_sql(data_dir),
        "COMMIT;",
        "",
    ]
    path.write_text("\n\n".join(statements), encoding="utf-8")


def _stage_and_upsert_sql(data_dir: Path) -> list[str]:
    return [
        *_table_sql("companies", COMPANY_COLUMNS, data_dir, _upsert_companies()),
        *_table_sql("users", USER_COLUMNS, data_dir, _upsert_users()),
        *_table_sql("warehouses", WAREHOUSE_COLUMNS, data_dir, _upsert_warehouses()),
        *_table_sql(
            "distributor_dealer_links",
            LINK_COLUMNS,
            data_dir,
            _upsert_distributor_dealer_links(),
        ),
        *_table_sql(
            "leasing_companies",
            LEASING_COMPANY_COLUMNS,
            data_dir,
            _upsert_leasing_companies(),
        ),
        "SELECT pg_temp.refresh_seed_leasing_company_document_requirements();",
        *_table_sql("mark", MARK_COLUMNS, data_dir, _upsert_by_pk("mark", MARK_COLUMNS, "id")),
        *_table_sql("model", MODEL_COLUMNS, data_dir, _upsert_by_pk("model", MODEL_COLUMNS, "id")),
        *_table_sql(
            "generation",
            GENERATION_COLUMNS,
            data_dir,
            _upsert_by_pk("generation", GENERATION_COLUMNS, "id"),
        ),
        *_table_sql(
            "configuration",
            CONFIGURATION_COLUMNS,
            data_dir,
            _upsert_by_pk("configuration", CONFIGURATION_COLUMNS, "id"),
        ),
        *_table_sql(
            "modification",
            MODIFICATION_COLUMNS,
            data_dir,
            _upsert_by_pk("modification", MODIFICATION_COLUMNS, "complectation_id"),
        ),
        *_table_sql("options", OPTION_TSV_COLUMNS, data_dir, _upsert_options()),
        *_table_sql(
            "specifications",
            SPECIFICATION_TSV_COLUMNS,
            data_dir,
            _upsert_specifications(),
        ),
        *_table_sql("vehicles", VEHICLE_COLUMNS, data_dir, _upsert_vehicles()),
        *_table_sql(
            "vehicle_warehouses",
            VEHICLE_WAREHOUSE_COLUMNS,
            data_dir,
            _upsert_vehicle_warehouses(),
        ),
        *_table_sql(
            "leasing_applications",
            LEASING_APPLICATION_COLUMNS,
            data_dir,
            _upsert_leasing_applications(),
        ),
        *_table_sql(
            "leasing_company_applications",
            LCA_COLUMNS,
            data_dir,
            _upsert_lca(),
        ),
        *_table_sql(
            "application_vehicles",
            APPLICATION_VEHICLE_COLUMNS,
            data_dir,
            _upsert_application_vehicles(),
        ),
        *_table_sql(
            "exchange_requests",
            EXCHANGE_REQUEST_COLUMNS,
            data_dir,
            _upsert_exchange_requests(),
        ),
        *_table_sql(
            "exchange_bids",
            EXCHANGE_BID_COLUMNS,
            data_dir,
            _upsert_exchange_bids(),
        ),
    ]


def _full_import_cleanup_sql() -> str:
    return """
TRUNCATE TABLE
    exchange_bids,
    exchange_requests,
    application_vehicles,
    leasing_company_applications,
    leasing_applications,
    vehicle_warehouses,
    vehicles,
    warehouses,
    distributor_dealer_links,
    leasing_company_document_requirements,
    leasing_companies,
    users,
    companies,
    cities,
    specifications,
    options,
    modification,
    configuration,
    generation,
    model,
    mark
RESTART IDENTITY CASCADE;
""".strip()


def _table_sql(table: str, columns: list[str], data_dir: Path, upsert_sql: str) -> list[str]:
    stage = f"stg_{table}"
    col_defs = ", ".join(f"{_qi(column)} text" for column in columns)
    cols = ", ".join(_qi(column) for column in columns)
    return [
        f"CREATE TEMP TABLE {stage} ({col_defs}) ON COMMIT DROP;",
        (
            f"\\copy {stage} ({cols}) FROM '{_sql_path(data_dir / f'{table}.tsv')}' "
            "WITH (FORMAT text, DELIMITER E'\\t', NULL '\\N')"
        ),
        upsert_sql,
    ]


def _upsert_companies() -> str:
    return """
INSERT INTO companies (
    id, name, inn, kpp, ogrn, company_type, address, contact_info,
    legal_address, actual_address, phone, email, website, is_active,
    full_name, short_name, okpo, okato, legal_form, region, city,
    registration_date, employees_count, main_okved_code, main_okved_description,
    director_full_name, bank_bik, bank_name, authorized_capital, net_profit,
    reporting_year, tax_system, enrichment_status, created_at, updated_at
)
SELECT
    id::uuid, name, inn, kpp, ogrn, company_type::company_type,
    address::jsonb, contact_info::jsonb, legal_address, actual_address,
    phone, email, website, is_active::boolean, full_name, short_name,
    okpo, okato, legal_form, region, city, registration_date::date,
    employees_count::integer, main_okved_code, main_okved_description,
    director_full_name, bank_bik, bank_name, authorized_capital::bigint,
    net_profit::bigint, reporting_year::integer, tax_system, enrichment_status,
    created_at::timestamptz, updated_at::timestamptz
FROM stg_companies
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    company_type = EXCLUDED.company_type,
    legal_address = EXCLUDED.legal_address,
    actual_address = EXCLUDED.actual_address,
    phone = EXCLUDED.phone,
    email = EXCLUDED.email,
    updated_at = EXCLUDED.updated_at;
""".strip()


def _upsert_users() -> str:
    return """
INSERT INTO users (
    id, email, password_hash, name, role, company_id, phone, is_active,
    email_verified, phone_verified, mfa_enabled, created_at, updated_at
)
SELECT
    id::uuid, email, password_hash, name, role::user_role, company_id::uuid,
    phone, is_active::boolean, email_verified::boolean, phone_verified::boolean,
    false, created_at::timestamptz, updated_at::timestamptz
FROM stg_users
ON CONFLICT (phone) DO UPDATE SET
    email = EXCLUDED.email,
    name = EXCLUDED.name,
    role = EXCLUDED.role,
    company_id = EXCLUDED.company_id,
    is_active = EXCLUDED.is_active,
    updated_at = EXCLUDED.updated_at;
""".strip()


def _upsert_cities() -> str:
    return """
INSERT INTO cities (id, name, created_at)
SELECT id::uuid, name, created_at::timestamptz
FROM stg_cities
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;
""".strip()


def _upsert_warehouses() -> str:
    return """
INSERT INTO warehouses (
    id, address, brand, city_id, dealer_id, company_id, status, created_at, updated_at
)
SELECT
    id::uuid, address, brand, city_id::uuid, dealer_id::uuid, company_id::uuid,
    status, created_at::timestamptz, updated_at::timestamptz
FROM stg_warehouses
ON CONFLICT (id) DO UPDATE SET
    address = EXCLUDED.address,
    brand = EXCLUDED.brand,
    city_id = EXCLUDED.city_id,
    dealer_id = EXCLUDED.dealer_id,
    company_id = EXCLUDED.company_id,
    status = EXCLUDED.status,
    updated_at = EXCLUDED.updated_at;
""".strip()


def _upsert_distributor_dealer_links() -> str:
    return """
INSERT INTO distributor_dealer_links (
    distributor_company_id, dealer_company_id, created_at
)
SELECT distributor_company_id::uuid, dealer_company_id::uuid, created_at::timestamptz
FROM stg_distributor_dealer_links
ON CONFLICT (distributor_company_id, dealer_company_id) DO NOTHING;
""".strip()


def _upsert_leasing_companies() -> str:
    return """
INSERT INTO leasing_companies (id, company_id, is_active, created_at, updated_at)
SELECT
    id::uuid, company_id::uuid, is_active::boolean,
    created_at::timestamptz, updated_at::timestamptz
FROM stg_leasing_companies
ON CONFLICT (id) DO UPDATE SET
    company_id = EXCLUDED.company_id,
    is_active = EXCLUDED.is_active,
    updated_at = EXCLUDED.updated_at;
""".strip()


def _upsert_by_pk(table: str, columns: list[str], pk: str) -> str:
    insert_cols = ", ".join(_qi(column) for column in columns)
    select_cols = ", ".join(_typed_select(column) for column in columns)
    update_cols = [
        f"{_qi(column)} = EXCLUDED.{_qi(column)}"
        for column in columns
        if column != pk
    ]
    update_sql = ", ".join(update_cols) if update_cols else f"{_qi(pk)} = EXCLUDED.{_qi(pk)}"
    sql = f"""
INSERT INTO {table} ({insert_cols})
SELECT {select_cols}
FROM stg_{table}
ON CONFLICT ({_qi(pk)}) DO UPDATE SET {update_sql};
"""
    return sql.strip()


def _upsert_options() -> str:
    return _upsert_by_pk("options", OPTION_TSV_COLUMNS, "complectation_id")


def _upsert_specifications() -> str:
    return _upsert_by_pk("specifications", SPECIFICATION_TSV_COLUMNS, "complectation_id")


def _upsert_vehicles() -> str:
    return """
INSERT INTO vehicles (
    id, vin, dealer_id, mark_id, model_id, generation_id, configuration_id,
    complectation_id, year, base_price, special_price, dealer_cost,
    discount_price, color, color_inter, images, status, is_available,
    created_at, updated_at
)
SELECT
    id::uuid, vin, dealer_id::uuid, mark_id, model_id, generation_id,
    configuration_id, complectation_id, year::integer, base_price::numeric,
    special_price::numeric, dealer_cost::numeric, discount_price::numeric,
    color, color_inter, images::jsonb, status, is_available::boolean,
    created_at::timestamptz, updated_at::timestamptz
FROM stg_vehicles
ON CONFLICT (id) DO UPDATE SET
    vin = EXCLUDED.vin,
    dealer_id = EXCLUDED.dealer_id,
    mark_id = EXCLUDED.mark_id,
    model_id = EXCLUDED.model_id,
    generation_id = EXCLUDED.generation_id,
    configuration_id = EXCLUDED.configuration_id,
    complectation_id = EXCLUDED.complectation_id,
    year = EXCLUDED.year,
    base_price = EXCLUDED.base_price,
    special_price = EXCLUDED.special_price,
    dealer_cost = EXCLUDED.dealer_cost,
    discount_price = EXCLUDED.discount_price,
    color = EXCLUDED.color,
    color_inter = EXCLUDED.color_inter,
    images = EXCLUDED.images,
    status = EXCLUDED.status,
    is_available = EXCLUDED.is_available,
    updated_at = EXCLUDED.updated_at;
""".strip()


def _upsert_vehicle_warehouses() -> str:
    return """
INSERT INTO vehicle_warehouses (id, vehicle_id, warehouse_id, created_at)
SELECT id::uuid, vehicle_id::uuid, warehouse_id::uuid, created_at::timestamptz
FROM stg_vehicle_warehouses
ON CONFLICT (vehicle_id) DO UPDATE SET warehouse_id = EXCLUDED.warehouse_id;
""".strip()


def _upsert_leasing_applications() -> str:
    return """
INSERT INTO leasing_applications (
    id, display_number, company_id, dealer_company_id, vehicle_id, name, email,
    status, total_amount, down_payment, down_payment_percent, lease_term_months,
    monthly_payment, total_cost, markup, rate, selected_leasing_companies,
    questionnaire_completed, questionnaire_progress, current_stage, created_at, updated_at
)
SELECT
    id::uuid, display_number, company_id::uuid, dealer_company_id::uuid,
    vehicle_id::uuid, name, email, status::application_status,
    total_amount::numeric, down_payment::numeric, down_payment_percent::numeric,
    lease_term_months::integer, monthly_payment::numeric, total_cost::numeric,
    markup::numeric, rate::numeric, selected_leasing_companies::uuid[],
    questionnaire_completed::boolean, questionnaire_progress::integer,
    current_stage, created_at::timestamptz, updated_at::timestamptz
FROM stg_leasing_applications
ON CONFLICT (id) DO UPDATE SET
    display_number = EXCLUDED.display_number,
    company_id = EXCLUDED.company_id,
    dealer_company_id = EXCLUDED.dealer_company_id,
    vehicle_id = EXCLUDED.vehicle_id,
    status = EXCLUDED.status,
    selected_leasing_companies = EXCLUDED.selected_leasing_companies,
    updated_at = EXCLUDED.updated_at;
""".strip()


def _upsert_lca() -> str:
    return """
INSERT INTO leasing_company_applications (
    id, application_id, leasing_company_id, status, submitted_at, created_at, updated_at
)
SELECT
    id::uuid, application_id::uuid, leasing_company_id::uuid,
    status::leasing_company_application_status, submitted_at::timestamptz,
    created_at::timestamptz, updated_at::timestamptz
FROM stg_leasing_company_applications
ON CONFLICT (id) DO UPDATE SET
    application_id = EXCLUDED.application_id,
    leasing_company_id = EXCLUDED.leasing_company_id,
    status = EXCLUDED.status,
    submitted_at = EXCLUDED.submitted_at,
    updated_at = EXCLUDED.updated_at;
""".strip()


def _upsert_application_vehicles() -> str:
    return """
INSERT INTO application_vehicles (
    id, application_id, vehicle_id, modification_id, quantity, unit_price,
    total_price, vin, is_model_order, created_at
)
SELECT
    id::uuid, application_id::uuid, vehicle_id::uuid, modification_id,
    quantity::integer, unit_price::numeric, total_price::numeric, vin,
    is_model_order::boolean, created_at::timestamptz
FROM stg_application_vehicles
ON CONFLICT (application_id, vehicle_id) DO UPDATE SET
    modification_id = EXCLUDED.modification_id,
    quantity = EXCLUDED.quantity,
    unit_price = EXCLUDED.unit_price,
    total_price = EXCLUDED.total_price,
    vin = EXCLUDED.vin;
""".strip()


def _upsert_exchange_requests() -> str:
    return """
INSERT INTO exchange_requests (
    id, lc_user_id, vehicle_id, distributor_id, quantity, expiration_at,
    discount_type, discount_value, file_url, file_name, status, accepted_bid_id,
    batch_number, batch_index, created_at, updated_at
)
SELECT
    id::uuid, lc_user_id::uuid, vehicle_id::uuid, distributor_id::uuid,
    quantity::integer, (expiration_date::date + time '23:59:59') AT TIME ZONE 'Europe/Moscow', discount_type, discount_value::numeric,
    file_url, file_name, status, accepted_bid_id::uuid, batch_number::integer,
    batch_index::integer, created_at::timestamptz, updated_at::timestamptz
FROM stg_exchange_requests
ON CONFLICT (id) DO UPDATE SET
    status = EXCLUDED.status,
    accepted_bid_id = EXCLUDED.accepted_bid_id,
    updated_at = EXCLUDED.updated_at;
""".strip()


def _upsert_exchange_bids() -> str:
    return """
INSERT INTO exchange_bids (
    id, request_id, dealer_id, distributor_id, price, comment, is_accepted,
    kp_file_url, kp_file_name, kp_status, kp_dealer_comment, kp_sent_at,
    kp_responded_at, quantity, bid_file_url, bid_file_name, created_at, updated_at
)
SELECT
    id::uuid, request_id::uuid, dealer_id::uuid, distributor_id::uuid,
    price::numeric, comment, is_accepted::boolean, kp_file_url, kp_file_name,
    kp_status, kp_dealer_comment, kp_sent_at::timestamptz,
    kp_responded_at::timestamptz, quantity::integer, bid_file_url, bid_file_name,
    created_at::timestamptz, updated_at::timestamptz
FROM stg_exchange_bids
ON CONFLICT (id) DO UPDATE SET
    price = EXCLUDED.price,
    comment = EXCLUDED.comment,
    is_accepted = EXCLUDED.is_accepted,
    updated_at = EXCLUDED.updated_at;
""".strip()


def _read_lk_mart_rebuild_sql() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "scripts" / "full_import" / "lk_mart_rebuild.sql").read_text(
        encoding="utf-8"
    ).strip()


def _write_clickhouse_sql(path: Path, data_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tables = [
        "dwh_companies",
        "dwh_users",
        "dwh_vehicles",
        "dwh_leasing_company_applications",
        "dwh_application_vehicles",
        "dwh_exchange_requests",
        "dwh_exchange_bids",
    ]
    mart_tables = [
        "dm_distributor_warehouse",
        "dm_distributor_applications",
        "dm_distributor_financials",
        "dm_distributor_exchange",
        "dm_distributor_sales_dc",
        "dm_distributor_sales_dc_regions",
    ]
    lines = ["SET max_partitions_per_insert_block = 10000;", ""]
    lines.extend(f"TRUNCATE TABLE {table};" for table in [*tables, *mart_tables])
    lines.append("")
    lines.extend(
        f"INSERT INTO {table} FROM INFILE '{_sql_path(data_dir / f'{table}.jsonl')}' FORMAT JSONEachRow;"
        for table in tables
    )
    lines.extend(["", "-- Rebuild leasing-company analytics marts after raw DWH load."])
    lines.append(_read_lk_mart_rebuild_sql())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_clickhouse_docker_loader(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / "lk_mart_rebuild.sql").write_text(
        _read_lk_mart_rebuild_sql() + "\n",
        encoding="utf-8",
    )
    tables = [
        "dwh_companies",
        "dwh_users",
        "dwh_vehicles",
        "dwh_leasing_company_applications",
        "dwh_application_vehicles",
        "dwh_exchange_requests",
        "dwh_exchange_bids",
    ]
    loop_body = "\n".join(
        [
            "for table in " + " ".join(tables) + "; do",
            '  echo "truncating ${table}"',
            "  docker compose -f docker-compose.dev.yml exec -T clickhouse \\",
            "    clickhouse-client --password password --database carcraft_dwh \\",
            '    --query "TRUNCATE TABLE ${table}"',
            '  echo "loading ${table}"',
            "  docker compose -f docker-compose.dev.yml exec -T clickhouse \\",
            "    clickhouse-client --password password --database carcraft_dwh \\",
            "    --max_partitions_per_insert_block=10000 \\",
            '    --query "INSERT INTO ${table} FORMAT JSONEachRow" \\',
            '    < "${BASE}/${table}.jsonl"',
            "done",
        ]
    )
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
                'BASE="${BASE:-${SCRIPT_DIR}/data}"',
                "for table in dm_distributor_warehouse dm_distributor_applications dm_distributor_financials dm_distributor_exchange dm_distributor_sales_dc dm_distributor_sales_dc_regions; do",
                '  echo "truncating ${table}"',
                "  docker compose -f docker-compose.dev.yml exec -T clickhouse \\",
                "    clickhouse-client --password password --database carcraft_dwh \\",
                '    --query "TRUNCATE TABLE ${table}"',
                "done",
                loop_body,
                'echo "rebuilding leasing-company analytics marts"',
                "docker compose -f docker-compose.dev.yml exec -T clickhouse \\",
                "  clickhouse-client --password password --database carcraft_dwh --multiquery \\",
                '  < "${SCRIPT_DIR}/lk_mart_rebuild.sql"',
                "for table in dm_lk_daily_metrics dm_lk_application_funnel dm_lk_proposals dm_lk_financial_pipeline; do",
                "  docker compose -f docker-compose.dev.yml exec -T clickhouse \\",
                "    clickhouse-client --password password --database carcraft_dwh \\",
                '    --query "SELECT \'${table}=\' || toString(count()) FROM ${table}"',
                "done",
                "",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _typed_select(column: str) -> str:
    quoted = _qi(column)
    int_columns = {
        "popular",
        "year_from",
        "year_to",
        "year_start",
        "year_stop",
        "is_restyle",
        "doors_count",
    }
    numeric_columns = {"offers_price_from", "offers_price_to"}
    if column in int_columns:
        return f"{quoted}::integer"
    if column in numeric_columns:
        return f"{quoted}::numeric"
    return quoted


def _read_csv(path: Path) -> Iterable[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        sample = file_obj.read(4096)
        file_obj.seek(0)
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
        reader = csv.DictReader(file_obj, delimiter=delimiter)
        return [dict(row) for row in reader]


def _iter_xlsx_rows(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet in workbook.worksheets:
            rows = sheet.iter_rows(values_only=True)
            try:
                raw_headers = next(rows)
            except StopIteration:
                continue
            headers = [str(value) if value is not None else "" for value in raw_headers]
            if not any(headers):
                continue
            for offset, values in enumerate(rows, start=2):
                if not any(value not in (None, "") for value in values):
                    continue
                yield offset, dict(zip(headers, values, strict=False))
            return
    finally:
        workbook.close()


def _source_file_manifest(
    full_dir: Path,
    catalog_dir: Path,
    image_source_paths: Iterable[Path],
) -> dict[str, dict[str, str | int]]:
    paths = [
        full_dir / "companies_clients.csv",
        full_dir / "companies_distributor_dealer.csv",
        full_dir / "companies.csv",
        full_dir / "companies_dealers.csv",
        full_dir / "distributor_dealer_links.csv",
        full_dir / "users.csv",
        full_dir / "warehouses.csv",
        full_dir / "catalog_mini.csv",
        full_dir / "vehicles_master.csv",
        full_dir / "lca.csv",
        full_dir / "exchange_requests.csv",
        full_dir / "exchange_bids.csv",
        *sorted(catalog_dir.glob("*.xlsx")),
        *image_source_paths,
    ]
    result: dict[str, dict[str, str | int]] = {}
    for path in paths:
        if path.exists():
            result[str(path)] = {
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
    return result


def _write_manifest(path: Path, manifest: BulkManifest) -> None:
    payload = {
        "generated_at": manifest.generated_at,
        "source_files": manifest.source_files,
        "row_counts": dict(sorted(manifest.row_counts.items())),
        "anomalies": manifest.anomalies,
        "application_ids": sorted(manifest.application_ids),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _reset_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.rglob("*"):
        if path.is_file():
            path.unlink()


def _add_anomaly(
    manifest: BulkManifest, strict: bool, anomaly: dict[str, str]
) -> None:
    manifest.anomalies.append(anomaly)
    if strict:
        raise ValueError(f"Strict bulk import anomaly: {anomaly}")


def _company_type(value: Any) -> str:
    raw = (_string(value) or "other").lower()
    return raw if raw in {"dealer", "leasing_company", "distributor", "other"} else "other"


def _user_role(value: Any) -> str:
    raw = (_string(value) or "client").lower()
    allowed = {
        "carcraft_employee",
        "dealer",
        "client",
        "leasing_company",
        "distributor",
        "external_api",
    }
    return raw if raw in allowed else "client"


def _application_status(value: Any) -> str:
    raw = (_string(value) or "active").lower()
    return raw if raw in APPLICATION_STATUS_VALUES else "active"


def _lca_status(value: Any) -> str:
    raw = (_string(value) or "under_review").lower()
    aliases = {
        "approved": "approved_final",
        "rejected": "rejected_approved",
        "review": "under_review",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in LCA_STATUS_VALUES else "under_review"


def _parent_status_from_lca(value: Any) -> str:
    status = _lca_status(value)
    if status in {
        "approved_final",
        "approved_final_another_cond",
        "selected_lc",
        "deal",
        "closed",
    }:
        return "issued"
    if status in {"rejected_approved", "rejected_prescoring"}:
        return "rejected"
    return "active"


def _city_from_row(row: Mapping[str, Any]) -> str:
    city = _string(row.get("city"))
    if city:
        return city
    address = _string(row.get("address"))
    if address and "," in address:
        return address.split(",", maxsplit=1)[0].strip() or "Unknown"
    return address or "Unknown"


def _normalize_uuid(value: Any) -> str | None:
    text = _string(value)
    if not text:
        return None
    try:
        return str(uuid.UUID(text))
    except ValueError:
        return None


def _string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text or None


def _bool(value: Any, *, default: bool | None = None) -> bool | None:
    text = _string(value)
    if text is None:
        return default
    lowered = text.lower()
    if lowered in {"1", "true", "t", "yes", "y", "да", "active"}:
        return True
    if lowered in {"0", "false", "f", "no", "n", "нет", "inactive"}:
        return False
    return default


def _uint(value: Any) -> int:
    return 1 if _bool(value, default=False) else 0


def _int(value: Any) -> int | None:
    text = _string(value)
    if text is None:
        return None
    try:
        return int(float(text.replace(" ", "").replace(",", ".")))
    except ValueError:
        return None


def _decimal(value: Any) -> Decimal | None:
    text = _string(value)
    if text is None:
        return None
    try:
        return Decimal(text.replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _capped_decimal(value: Any, *, cap: Decimal = Decimal("2500000")) -> Decimal | None:
    parsed = _decimal(value)
    if parsed is None:
        return None
    return min(parsed, cap)


def _date(value: Any) -> str | None:
    text = _string(value)
    if text is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        return text[:10] if len(text) >= 10 else None


def _datetime(value: Any) -> str | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = _string(value)
        if text is None:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.isoformat()


def _submitted_at(
    row: Mapping[str, Any],
    created_at: str,
    lca_id: str,
    application_id: str,
) -> str:
    explicit = _datetime(row.get("submitted_at"))
    if explicit is not None:
        return explicit

    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)

    status = _lca_status(row.get("status"))
    seed = f"{application_id}:{lca_id}:{status}"
    if status == "deal":
        days = 7 + _stable_index(seed, 39)
    elif status.startswith("rejected"):
        days = 2 + _stable_index(seed, 20)
    else:
        days = 1 + _stable_index(seed, 14)

    submitted = created - timedelta(days=days)
    floor = datetime(2000, 1, 2, tzinfo=created.tzinfo)
    submitted = max(submitted, floor)
    if floor < created <= submitted:
        submitted = created - timedelta(days=1)
    return submitted.isoformat()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _json_default(value: Any) -> str | int | float | None:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _pg_uuid_array(values: list[str]) -> str:
    return "{" + ",".join(values) + "}"


def _to_tsv_value(value: Any) -> str:
    if value is None:
        return r"\N"
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, Decimal):
        text = str(value)
    elif isinstance(value, datetime | date):
        text = value.isoformat()
    else:
        text = str(value)
    return (
        text.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _qi(identifier: str) -> str:
    return f'"{identifier}"' if identifier == "class" else identifier


def _sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-dir", type=Path, default=DEFAULT_FULL_DIR)
    parser.add_argument("--catalog-dir", type=Path, default=DEFAULT_CATALOG_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--image-source",
        action="append",
        type=Path,
        default=[],
        help="XLSX file with real catalog image values. Can be passed multiple times.",
    )
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    manifest = generate_artifacts(
        full_dir=args.full_dir,
        catalog_dir=args.catalog_dir,
        output_dir=args.output_dir,
        image_source_paths=args.image_source,
        strict=args.strict,
    )
    sys.stdout.write(
        json.dumps(
            {
                "output_dir": str(args.output_dir.resolve()),
                "row_counts": manifest.row_counts,
                "anomalies": len(manifest.anomalies),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

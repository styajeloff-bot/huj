from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

CLIENT_HEADERS = [
    "client_key",
    "company_name",
    "company_inn",
    "company_email",
    "company_phone",
    "director",
    "user_name",
    "user_email",
    "user_phone",
]

LEASING_COMPANY_HEADERS = [
    "lc_key",
    "company_name",
    "company_inn",
    "company_email",
    "company_phone",
    "average_down_payment_percent",
    "average_lease_term_months",
    "average_markup_percent",
    "min_down_payment_percent",
    "max_lease_term_months",
]

GROUP_HEADERS = [
    "group_key",
    "client_key",
    "created_at",
]

APPLICATION_HEADERS = [
    "application_key",
    "client_key",
    "group_key",
    "name",
    "email",
    "company_name_or_inn",
    "status",
    "lc_link_status",
    "leasing_company_keys",
    "total_amount",
    "down_payment",
    "down_payment_percent",
    "lease_term_months",
    "monthly_payment",
    "total_cost",
    "markup",
    "rate",
    "total_interest",
    "buyout_amount",
    "vat_refund",
    "profit_tax_savings",
    "total_savings",
    "current_stage",
    "questionnaire_completed",
    "questionnaire_progress",
    "created_at",
    "updated_at",
]

VEHICLE_HEADERS = [
    "application_key",
    "vehicle_id",
    "modification_id",
    "quantity",
    "unit_price",
    "total_price",
    "comment",
    "is_model_order",
]

README_ROWS = [
    (
        "Sheet",
        "Purpose",
        "Required columns",
        "Notes",
    ),
    (
        "clients",
        "Client companies and client users",
        "client_key, company_name, user_phone",
        "One row = one client company + one client user. user_phone must be unique.",
    ),
    (
        "leasing_companies",
        "Leasing company directory",
        "lc_key, company_name",
        "One row = one company in companies + one row in leasing_companies.",
    ),
    (
        "groups",
        "Application groups",
        "group_key, client_key",
        "Each group belongs to one client user.",
    ),
    (
        "applications",
        "Leasing applications",
        "application_key, client_key, group_key, status, leasing_company_keys",
        "leasing_company_keys is comma-separated lc_key list, e.g. LC_MAIN,LC_RESERVE. Empty value creates an application without LC links.",
    ),
    (
        "vehicles",
        "Application vehicles",
        "application_key, modification_id or vehicle_id, quantity",
        "For mass load use modification_id + is_model_order=true.",
    ),
]

VALID_APP_STATUSES = {
    "draft",
    "submitted",
    "under_review",
    "approved",
    "rejected",
    "issued",
    "closed",
    "documents_required",
    "pending_distribution",
}

VALID_LC_STATUSES = {
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

CLIENT_COLUMN_ALIASES = {
    "CLIENT_KEY": "client_key",
    "login_email": "user_email",
    "login_phone": "user_phone",
}

PROPOSAL_STATUSES = {"approved_scoring", "approved_scoring_another_cond", "approved_final", "approved_final_another_cond", "deal"}
FINAL_SUBMITTED_LC_STATUSES = {"approved_final", "approved_final_another_cond", "rejected_approved", "closed", "deal"}

MIGRATION_TEMPLATE = '''"""{message}

The seed SQL is generated from {workbook_path} by
scripts/leasing_seed_workbook.py and stored next to this migration as a
companion .sql file to keep this migration readable.
"""

from pathlib import Path

from alembic import op

revision: str = "{revision}"
down_revision: str | None = "{down_revision}"
branch_labels = None
depends_on = None


def _seed_sql() -> str:
    sql_path = Path(__file__).with_name("{sql_filename}")
    sql = sql_path.read_text(encoding="utf-8").strip()
    lines = [
        line
        for line in sql.splitlines()
        if line.strip().upper() not in {{"BEGIN;", "COMMIT;"}}
    ]
    return "\\n".join(lines).strip()


def _split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    index = 0

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if not in_single_quote and char == "-" and next_char == "-":
            newline = sql.find("\\n", index)
            end = len(sql) if newline == -1 else newline
            current.append(sql[index:end])
            index = end
            continue

        current.append(char)

        if char == "'":
            if in_single_quote and next_char == "'":
                current.append(next_char)
                index += 2
                continue
            in_single_quote = not in_single_quote
        elif char == ";" and not in_single_quote:
            statement = "".join(current).strip()
            if _is_executable_statement(statement):
                statements.append(statement)
            current = []

        index += 1

    tail = "".join(current).strip()
    if _is_executable_statement(tail):
        statements.append(tail)

    return statements


def _is_executable_statement(statement: str) -> bool:
    for line in statement.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return True
    return False


def upgrade() -> None:
    connection = op.get_bind()
    statements = _split_sql_statements(_seed_sql())
    for index, statement in enumerate(statements, start=1):
        try:
            connection.exec_driver_sql(statement)
        except Exception as exc:
            preview = " ".join(statement.split())[:500]
            original = getattr(exc, "orig", exc)
            raise RuntimeError(
                f"Failed to execute leasing upload seed statement #{{index}}/{{len(statements)}}: "
                f"{{preview}}. Error: {{original}}"
            ) from None


def downgrade() -> None:
    # Seed migrations are intentionally not reversed automatically: the data
    # may be edited by users after insertion, so deleting it on downgrade would
    # be unsafe.
    pass
'''


@dataclass(frozen=True)
class SheetData:
    headers: list[str]
    rows: list[dict[str, str]]


def _stderr(message: str) -> None:
    sys.stderr.write(f"{message}\n")


def _normalise_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def _parse_bool(value: str, *, default: bool = False) -> bool:
    if not value:
        return default
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def _parse_int(value: str, *, default: int | None = None) -> int | None:
    if not value:
        return default
    return int(value)


def _parse_optional_int(value: str) -> int | None:
    if not value:
        return None
    return int(value) if value.isdigit() else None


def _parse_decimal(value: str) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal value: {value}") from exc


def _parse_csv_list(value: str) -> list[str]:
    if not value:
        return []
    reader = csv.reader(io.StringIO(value))
    parsed = next(reader, [])
    return [item.strip() for item in parsed if item.strip()]


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, int):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _write_sheet(
    workbook: Workbook,
    *,
    title: str,
    headers: list[str],
    rows: list[list[Any]],
) -> None:
    sheet = workbook.create_sheet(title)
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(row)
    sheet.freeze_panes = "A2"
    for index, header in enumerate(headers, start=1):
        width = max(len(header) + 2, 18)
        sheet.column_dimensions[get_column_letter(index)].width = width


def create_template(path: Path) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)

    _write_sheet(
        workbook,
        title="README",
        headers=list(README_ROWS[0]),
        rows=[list(row) for row in README_ROWS[1:]],
    )
    _write_sheet(
        workbook,
        title="clients",
        headers=CLIENT_HEADERS,
        rows=[
            [
                "CLIENT_MAIN",
                "ООО Тестовый клиент",
                "7700000001",
                "office@test-client.local",
                "+74950000001",
                "Иванов Иван Иванович",
                "Тестовый клиент",
                "test-client.local@example.com",
                "+79990000001",
            ]
        ],
    )
    _write_sheet(
        workbook,
        title="leasing_companies",
        headers=LEASING_COMPANY_HEADERS,
        rows=[
            [
                "LC_MAIN",
                "ООО Тестовая ЛК",
                "7700000002",
                "office@test-lc.local",
                "+74950000002",
                "20",
                "48",
                "11.5",
                "10",
                "84",
            ]
        ],
    )
    _write_sheet(
        workbook,
        title="groups",
        headers=GROUP_HEADERS,
        rows=[
            ["GROUP_001", "CLIENT_MAIN", "2026-04-01T10:00:00+03:00"],
            ["GROUP_002", "CLIENT_MAIN", "2026-04-02T10:00:00+03:00"],
        ],
    )
    _write_sheet(
        workbook,
        title="applications",
        headers=APPLICATION_HEADERS,
        rows=[
            [
                "APP_000001",
                "CLIENT_MAIN",
                "GROUP_001",
                "Заявка 1",
                "leasing@test-client.local",
                "ООО Тестовый клиент / 7700000001",
                "submitted",
                "under_review",
                "LC_MAIN",
                "2500000",
                "500000",
                "20",
                "48",
                "65000",
                "3120000",
                "9.5",
                "14.2",
                "620000",
                "1000",
                "120000",
                "70000",
                "190000",
                "leasing_companies",
                "true",
                "100",
                "2026-04-01T10:00:00+03:00",
                "2026-04-01T10:00:00+03:00",
            ],
            [
                "APP_000002",
                "CLIENT_MAIN",
                "GROUP_001",
                "Заявка 2",
                "leasing@test-client.local",
                "ООО Тестовый клиент / 7700000001",
                "approved",
                "approved_final",
                "LC_MAIN",
                "3300000",
                "800000",
                "24",
                "36",
                "87000",
                "3900000",
                "8.0",
                "13.1",
                "560000",
                "1000",
                "140000",
                "90000",
                "230000",
                "leasing_companies",
                "true",
                "100",
                "2026-04-02T10:00:00+03:00",
                "2026-04-02T10:00:00+03:00",
            ],
        ],
    )
    _write_sheet(
        workbook,
        title="vehicles",
        headers=VEHICLE_HEADERS,
        rows=[
            ["APP_000001", "", "TEST-MOD-0001", "1", "2500000", "2500000", "Основной предмет лизинга", "true"],
            ["APP_000002", "", "TEST-MOD-0002", "2", "1650000", "3300000", "Две единицы техники", "true"],
        ],
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def _read_sheet(workbook_path: Path, sheet_name: str) -> SheetData:
    workbook = load_workbook(workbook_path, data_only=True, read_only=True)
    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"Workbook sheet not found: {sheet_name}")
    sheet = workbook[sheet_name]
    rows_iter = sheet.iter_rows(values_only=True)
    header_row = next(rows_iter, None)
    if header_row is None:
        raise ValueError(f"Workbook sheet is empty: {sheet_name}")
    raw_headers = [_normalise_cell(cell) for cell in header_row]
    aliases = CLIENT_COLUMN_ALIASES if sheet_name == "clients" else {}
    headers = [aliases.get(header, header) for header in raw_headers]
    rows: list[dict[str, str]] = []
    for raw_row in rows_iter:
        values = [_normalise_cell(cell) for cell in raw_row]
        if not any(values):
            continue
        rows.append(
            {
                headers[index]: values[index] if index < len(values) else ""
                for index in range(len(headers))
            }
        )
    return SheetData(headers=headers, rows=rows)


def _require_columns(sheet: SheetData, required: list[str], *, sheet_name: str) -> None:
    missing = [column for column in required if column not in sheet.headers]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Missing columns in {sheet_name}: {joined}")


def _ensure_unique_keys(rows: list[dict[str, str]], key_name: str, *, sheet_name: str) -> None:
    seen: set[str] = set()
    for row in rows:
        key = row.get(key_name, "")
        if not key:
            raise ValueError(f"Empty {key_name} in {sheet_name}")
        if key in seen:
            raise ValueError(f"Duplicate {key_name}={key} in {sheet_name}")
        seen.add(key)


def _validate_client_rows(clients: SheetData) -> None:
    for row in clients.rows:
        if not row.get("company_name"):
            raise ValueError("clients.company_name is required")
        if not row.get("user_phone"):
            raise ValueError("clients.user_phone is required")


def _validate_group_rows(groups: SheetData, client_keys: set[str]) -> None:
    for row in groups.rows:
        if row["client_key"] not in client_keys:
            raise ValueError(
                f"groups.client_key references unknown client_key={row['client_key']}"
            )


def _validate_application_rows(
    applications: SheetData,
    client_keys: set[str],
    group_keys: set[str],
    lc_keys: set[str],
) -> None:
    for row in applications.rows:
        if row["client_key"] not in client_keys:
            raise ValueError(
                f"applications.client_key references unknown client_key={row['client_key']}"
            )
        if row["group_key"] not in group_keys:
            raise ValueError(
                f"applications.group_key references unknown group_key={row['group_key']}"
            )
        if row["status"] not in VALID_APP_STATUSES:
            raise ValueError(f"Invalid applications.status={row['status']}")
        lc_status = row.get("lc_link_status", "") or _default_lc_status(row["status"])
        if lc_status not in VALID_LC_STATUSES:
            raise ValueError(f"Invalid applications.lc_link_status={lc_status}")
        row_lc_keys = _parse_csv_list(row["leasing_company_keys"])
        for lc_key in row_lc_keys:
            if lc_key not in lc_keys:
                raise ValueError(
                    f"applications.leasing_company_keys references unknown lc_key={lc_key}"
                )


def _validate_vehicle_rows(vehicles: SheetData, application_keys: set[str]) -> None:
    for row in vehicles.rows:
        if row["application_key"] not in application_keys:
            raise ValueError(
                f"vehicles.application_key references unknown application_key={row['application_key']}"
            )
        if not row.get("modification_id") and _parse_optional_int(row.get("vehicle_id", "")) is None:
            raise ValueError(
                "vehicles requires modification_id or numeric vehicle_id for every row"
            )


def _validate_workbook(
    clients: SheetData,
    leasing_companies: SheetData,
    groups: SheetData,
    applications: SheetData,
    vehicles: SheetData,
) -> None:
    _require_columns(clients, ["client_key", "company_name", "user_phone"], sheet_name="clients")
    _require_columns(leasing_companies, ["lc_key", "company_name"], sheet_name="leasing_companies")
    _require_columns(groups, ["group_key", "client_key"], sheet_name="groups")
    _require_columns(
        applications,
        ["application_key", "client_key", "group_key", "status", "leasing_company_keys"],
        sheet_name="applications",
    )
    _require_columns(
        vehicles,
        ["application_key", "quantity"],
        sheet_name="vehicles",
    )

    _ensure_unique_keys(clients.rows, "client_key", sheet_name="clients")
    _ensure_unique_keys(leasing_companies.rows, "lc_key", sheet_name="leasing_companies")
    _ensure_unique_keys(groups.rows, "group_key", sheet_name="groups")
    _ensure_unique_keys(applications.rows, "application_key", sheet_name="applications")

    client_keys = {row["client_key"] for row in clients.rows}
    lc_keys = {row["lc_key"] for row in leasing_companies.rows}
    group_keys = {row["group_key"] for row in groups.rows}
    application_keys = {row["application_key"] for row in applications.rows}

    _validate_client_rows(clients)
    _validate_group_rows(groups, client_keys)
    _validate_application_rows(applications, client_keys, group_keys, lc_keys)
    _validate_vehicle_rows(vehicles, application_keys)


def _default_lc_status(application_status: str) -> str:
    if application_status in {"submitted", "under_review", "pending_distribution", "draft"}:
        return "under_review"
    status_map = {
        "under_review_with_docs": "under_review_with_docs",
        "documents_required": "documents_required",
        "approved": "approved_final",
        "closed": "closed",
        "rejected": "rejected_approved",
        "issued": "deal",
    }
    return status_map.get(application_status, "approved_final")


def _group_application_keys(
    applications: list[dict[str, str]],
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in applications:
        grouped[row["group_key"]].append(row["application_key"])
    return grouped


def _default_timestamp(offset_seconds: int) -> str:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return (base + timedelta(seconds=offset_seconds)).isoformat()


def _values_block(rows: list[list[Any]]) -> str:
    return ",\n".join(
        f"    ({', '.join(_sql_literal(value) for value in row)})" for row in rows
    )


def _insert_values_sql(
    *,
    header_lines: list[str],
    rows: list[list[Any]],
    chunk_size: int = 500,
) -> str:
    statements: list[str] = []
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        statements.append("\n".join([*header_lines, f"{_values_block(chunk)};"]))
    return "\n\n".join(statements)


def generate_sql(workbook_path: Path) -> str:
    clients = _read_sheet(workbook_path, "clients")
    leasing_companies = _read_sheet(workbook_path, "leasing_companies")
    groups = _read_sheet(workbook_path, "groups")
    applications = _read_sheet(workbook_path, "applications")
    vehicles = _read_sheet(workbook_path, "vehicles")

    _validate_workbook(clients, leasing_companies, groups, applications, vehicles)

    client_rows = [
        [
            row["client_key"],
            row["company_name"],
            row.get("company_inn") or None,
            row.get("company_email") or None,
            row.get("company_phone") or None,
            row.get("director") or None,
            row.get("user_name") or row.get("director") or None,
            row.get("user_email") or None,
            row["user_phone"],
        ]
        for row in clients.rows
    ]

    lc_rows = [
        [
            row["lc_key"],
            row["company_name"],
            row.get("company_inn") or None,
            row.get("company_email") or None,
            row.get("company_phone") or None,
            _parse_int(row.get("average_down_payment_percent", ""), default=30),
            _parse_int(row.get("average_lease_term_months", ""), default=72),
            _parse_decimal(row.get("average_markup_percent", "") or "10.0"),
            _parse_int(row.get("min_down_payment_percent", ""), default=10),
            _parse_int(row.get("max_lease_term_months", ""), default=84),
        ]
        for row in leasing_companies.rows
    ]

    group_rows: list[list[Any]] = []
    app_keys_by_group = _group_application_keys(applications.rows)
    for index, row in enumerate(groups.rows, start=1):
        created_at = row.get("created_at") or _default_timestamp(index * 10)
        group_rows.append(
            [
                row["group_key"],
                row["client_key"],
                created_at,
                ",".join(app_keys_by_group.get(row["group_key"], [])),
            ]
        )

    application_rows: list[list[Any]] = []
    for index, row in enumerate(applications.rows, start=1):
        created_at = row.get("created_at") or _default_timestamp(index)
        updated_at = row.get("updated_at") or created_at
        application_rows.append(
            [
                row["application_key"],
                row["client_key"],
                row["group_key"],
                row.get("name") or row["application_key"],
                row.get("email") or None,
                row.get("company_name_or_inn") or None,
                row["status"],
                row.get("lc_link_status") or _default_lc_status(row["status"]),
                ",".join(_parse_csv_list(row["leasing_company_keys"])),
                _parse_decimal(row.get("total_amount", "")),
                _parse_decimal(row.get("down_payment", "")),
                _parse_decimal(row.get("down_payment_percent", "")),
                _parse_int(row.get("lease_term_months", ""), default=None),
                _parse_decimal(row.get("monthly_payment", "")),
                _parse_decimal(row.get("total_cost", "")),
                _parse_decimal(row.get("markup", "")),
                _parse_decimal(row.get("rate", "")),
                _parse_decimal(row.get("total_interest", "")),
                _parse_decimal(row.get("buyout_amount", "")),
                _parse_decimal(row.get("vat_refund", "")),
                _parse_decimal(row.get("profit_tax_savings", "")),
                _parse_decimal(row.get("total_savings", "")),
                row.get("current_stage") or "leasing_companies",
                _parse_bool(row.get("questionnaire_completed", ""), default=True),
                _parse_int(row.get("questionnaire_progress", ""), default=100),
                created_at,
                updated_at,
            ]
        )

    vehicle_rows: list[list[Any]] = []
    for row in vehicles.rows:
        quantity = _parse_int(row.get("quantity", ""), default=1) or 1
        unit_price = _parse_decimal(row.get("unit_price", ""))
        total_price = _parse_decimal(row.get("total_price", ""))
        vehicle_id = _parse_optional_int(row.get("vehicle_id", ""))
        if total_price is None and unit_price is not None:
            total_price = unit_price * quantity
        vehicle_rows.append(
            [
                row["application_key"],
                vehicle_id,
                row.get("modification_id") or None,
                quantity,
                unit_price or Decimal("0"),
                total_price or Decimal("0"),
                row.get("comment") or None,
                _parse_bool(row.get("is_model_order", ""), default=vehicle_id is None),
            ]
        )

    return "\n".join(
        [
            "BEGIN;",
            "",
            "-- Generated from leasing seed workbook.",
            "CREATE TEMP TABLE seed_clients (",
            "    client_key text PRIMARY KEY,",
            "    company_name text NOT NULL,",
            "    company_inn text NULL,",
            "    company_email text NULL,",
            "    company_phone text NULL,",
            "    director_full_name text NULL,",
            "    user_name text NULL,",
            "    user_email text NULL,",
            "    user_phone text NOT NULL",
            ") ON COMMIT DROP;",
            "",
            _insert_values_sql(
                header_lines=[
                    "INSERT INTO seed_clients (",
                    "    client_key, company_name, company_inn, company_email, company_phone,",
                    "    director_full_name, user_name, user_email, user_phone",
                    ") VALUES",
                ],
                rows=client_rows,
            ),
            "",
            "CREATE TEMP TABLE seed_lcs (",
            "    lc_key text PRIMARY KEY,",
            "    company_name text NOT NULL,",
            "    company_inn text NULL,",
            "    company_email text NULL,",
            "    company_phone text NULL,",
            "    average_down_payment_percent integer NULL,",
            "    average_lease_term_months integer NULL,",
            "    average_markup_percent numeric(5,2) NULL,",
            "    min_down_payment_percent integer NULL,",
            "    max_lease_term_months integer NULL",
            ") ON COMMIT DROP;",
            "",
            _insert_values_sql(
                header_lines=[
                    "INSERT INTO seed_lcs (",
                    "    lc_key, company_name, company_inn, company_email, company_phone,",
                    "    average_down_payment_percent, average_lease_term_months, average_markup_percent,",
                    "    min_down_payment_percent, max_lease_term_months",
                    ") VALUES",
                ],
                rows=lc_rows,
            ),
            "",
            "CREATE TEMP TABLE seed_groups (",
            "    group_key text PRIMARY KEY,",
            "    client_key text NOT NULL,",
            "    created_at timestamptz NULL,",
            "    application_keys_csv text NULL",
            ") ON COMMIT DROP;",
            "",
            _insert_values_sql(
                header_lines=[
                    "INSERT INTO seed_groups (group_key, client_key, created_at, application_keys_csv) VALUES",
                ],
                rows=group_rows,
            ),
            "",
            "CREATE TEMP TABLE seed_applications (",
            "    application_key text PRIMARY KEY,",
            "    client_key text NOT NULL,",
            "    group_key text NOT NULL,",
            "    name text NOT NULL,",
            "    email text NULL,",
            "    company_name_or_inn text NULL,",
            "    status application_status NOT NULL,",
            "    lc_link_status leasing_company_application_status NOT NULL,",
            "    leasing_company_keys_csv text NOT NULL,",
            "    total_amount numeric(15,2) NULL,",
            "    down_payment numeric(15,2) NULL,",
            "    down_payment_percent numeric(5,2) NULL,",
            "    lease_term_months integer NULL,",
            "    monthly_payment numeric(12,2) NULL,",
            "    total_cost numeric(15,2) NULL,",
            "    markup numeric(15,2) NULL,",
            "    rate numeric(5,2) NULL,",
            "    total_interest numeric(15,2) NULL,",
            "    buyout_amount numeric(15,2) NULL,",
            "    vat_refund numeric(15,2) NULL,",
            "    profit_tax_savings numeric(15,2) NULL,",
            "    total_savings numeric(15,2) NULL,",
            "    current_stage text NOT NULL,",
            "    questionnaire_completed boolean NOT NULL,",
            "    questionnaire_progress integer NOT NULL,",
            "    created_at timestamptz NULL,",
            "    updated_at timestamptz NULL",
            ") ON COMMIT DROP;",
            "",
            _insert_values_sql(
                header_lines=[
                    "INSERT INTO seed_applications (",
                    "    application_key, client_key, group_key, name, email, company_name_or_inn, status,",
                    "    lc_link_status, leasing_company_keys_csv, total_amount, down_payment,",
                    "    down_payment_percent, lease_term_months, monthly_payment, total_cost, markup, rate,",
                    "    total_interest, buyout_amount, vat_refund, profit_tax_savings, total_savings,",
                    "    current_stage, questionnaire_completed, questionnaire_progress, created_at, updated_at",
                    ") VALUES",
                ],
                rows=application_rows,
            ),
            "",
            "CREATE TEMP TABLE seed_vehicles (",
            "    application_key text NOT NULL,",
            "    vehicle_id integer NULL,",
            "    modification_id text NULL,",
            "    quantity integer NOT NULL,",
            "    unit_price numeric(15,2) NOT NULL,",
            "    total_price numeric(15,2) NOT NULL,",
            "    comment text NULL,",
            "    is_model_order boolean NOT NULL",
            ") ON COMMIT DROP;",
            "",
            _insert_values_sql(
                header_lines=[
                    "INSERT INTO seed_vehicles (",
                    "    application_key, vehicle_id, modification_id, quantity, unit_price, total_price,",
                    "    comment, is_model_order",
                    ") VALUES",
                ],
                rows=vehicle_rows,
            ),
            "",
            "-- Client companies",
            "INSERT INTO companies (",
            "    name, inn, company_type, phone, email, director_full_name, is_active",
            ")",
            "SELECT",
            "    sc.company_name,",
            "    sc.company_inn,",
            "    'other'::company_type,",
            "    sc.company_phone,",
            "    sc.company_email,",
            "    sc.director_full_name,",
            "    TRUE",
            "FROM seed_clients sc",
            "WHERE NOT EXISTS (",
            "    SELECT 1",
            "    FROM companies c",
            "    WHERE (sc.company_inn IS NOT NULL AND c.inn = sc.company_inn)",
            "       OR (sc.company_inn IS NULL AND c.company_type = 'other' AND c.name = sc.company_name)",
            ");",
            "",
            "UPDATE companies c",
            "SET",
            "    name = sc.company_name,",
            "    company_type = 'other'::company_type,",
            "    phone = coalesce(sc.company_phone, c.phone),",
            "    email = coalesce(sc.company_email, c.email),",
            "    director_full_name = coalesce(sc.director_full_name, c.director_full_name),",
            "    is_active = TRUE,",
            "    updated_at = CURRENT_TIMESTAMP",
            "FROM seed_clients sc",
            "WHERE (sc.company_inn IS NOT NULL AND c.inn = sc.company_inn)",
            "   OR (sc.company_inn IS NULL AND c.company_type = 'other' AND c.name = sc.company_name);",
            "",
            "CREATE TEMP TABLE seed_client_company_map ON COMMIT DROP AS",
            "SELECT",
            "    sc.client_key,",
            "    c.id AS company_id",
            "FROM seed_clients sc",
            "JOIN companies c",
            "    ON (sc.company_inn IS NOT NULL AND c.inn = sc.company_inn)",
            "    OR (sc.company_inn IS NULL AND c.company_type = 'other' AND c.name = sc.company_name);",
            "",
            "-- Client users",
            "INSERT INTO users (",
            "    email, name, role, company_id, company_name_or_inn, phone,",
            "    is_active, email_verified, phone_verified",
            ")",
            "SELECT",
            "    sc.user_email,",
            "    sc.user_name,",
            "    'client'::user_role,",
            "    cm.company_id,",
            "    sc.company_name,",
            "    sc.user_phone,",
            "    TRUE, TRUE, TRUE",
            "FROM seed_clients sc",
            "JOIN seed_client_company_map cm ON cm.client_key = sc.client_key",
            "WHERE TRUE",
            "ON CONFLICT (phone) DO UPDATE SET",
            "    email = EXCLUDED.email,",
            "    name = EXCLUDED.name,",
            "    role = EXCLUDED.role,",
            "    company_id = EXCLUDED.company_id,",
            "    company_name_or_inn = EXCLUDED.company_name_or_inn,",
            "    is_active = TRUE,",
            "    email_verified = TRUE,",
            "    phone_verified = TRUE,",
            "    updated_at = CURRENT_TIMESTAMP;",
            "",
            "CREATE TEMP TABLE seed_client_user_map ON COMMIT DROP AS",
            "SELECT",
            "    sc.client_key,",
            "    u.id AS user_id",
            "FROM seed_clients sc",
            "JOIN users u ON u.phone = sc.user_phone;",
            "",
            "-- Leasing companies",
            "INSERT INTO companies (",
            "    name, inn, company_type, phone, email, is_active",
            ")",
            "SELECT",
            "    sl.company_name,",
            "    sl.company_inn,",
            "    'leasing_company'::company_type,",
            "    sl.company_phone,",
            "    sl.company_email,",
            "    TRUE",
            "FROM seed_lcs sl",
            "WHERE NOT EXISTS (",
            "    SELECT 1",
            "    FROM companies c",
            "    WHERE (sl.company_inn IS NOT NULL AND c.inn = sl.company_inn)",
            "       OR (sl.company_inn IS NULL AND c.company_type = 'leasing_company' AND c.name = sl.company_name)",
            ");",
            "",
            "UPDATE companies c",
            "SET",
            "    name = sl.company_name,",
            "    company_type = 'leasing_company'::company_type,",
            "    phone = coalesce(sl.company_phone, c.phone),",
            "    email = coalesce(sl.company_email, c.email),",
            "    is_active = TRUE,",
            "    updated_at = CURRENT_TIMESTAMP",
            "FROM seed_lcs sl",
            "WHERE (sl.company_inn IS NOT NULL AND c.inn = sl.company_inn)",
            "   OR (sl.company_inn IS NULL AND c.company_type = 'leasing_company' AND c.name = sl.company_name);",
            "",
            "CREATE TEMP TABLE seed_lc_company_map ON COMMIT DROP AS",
            "SELECT",
            "    sl.lc_key,",
            "    c.id AS company_id",
            "FROM seed_lcs sl",
            "JOIN companies c",
            "    ON (sl.company_inn IS NOT NULL AND c.inn = sl.company_inn)",
            "    OR (sl.company_inn IS NULL AND c.company_type = 'leasing_company' AND c.name = sl.company_name);",
            "",
            "INSERT INTO leasing_companies (",
            "    company_id, average_down_payment_percent, average_lease_term_months,",
            "    average_markup_percent, min_down_payment_percent, max_lease_term_months, is_active",
            ")",
            "SELECT",
            "    cm.company_id,",
            "    sl.average_down_payment_percent,",
            "    sl.average_lease_term_months,",
            "    sl.average_markup_percent,",
            "    sl.min_down_payment_percent,",
            "    sl.max_lease_term_months,",
            "    TRUE",
            "FROM seed_lcs sl",
            "JOIN seed_lc_company_map cm ON cm.lc_key = sl.lc_key",
            "WHERE NOT EXISTS (",
            "    SELECT 1",
            "    FROM leasing_companies lc",
            "    WHERE lc.company_id = cm.company_id",
            ");",
            "",
            "UPDATE leasing_companies lc",
            "SET",
            "    average_down_payment_percent = sl.average_down_payment_percent,",
            "    average_lease_term_months = sl.average_lease_term_months,",
            "    average_markup_percent = sl.average_markup_percent,",
            "    min_down_payment_percent = sl.min_down_payment_percent,",
            "    max_lease_term_months = sl.max_lease_term_months,",
            "    is_active = TRUE,",
            "    updated_at = CURRENT_TIMESTAMP",
            "FROM seed_lcs sl",
            "JOIN seed_lc_company_map cm ON cm.lc_key = sl.lc_key",
            "WHERE lc.company_id = cm.company_id;",
            "",
            "CREATE TEMP TABLE seed_lc_map ON COMMIT DROP AS",
            "SELECT",
            "    sl.lc_key,",
            "    lc.id AS leasing_company_id,",
            "    sl.company_name",
            "FROM seed_lcs sl",
            "JOIN seed_lc_company_map cm ON cm.lc_key = sl.lc_key",
            "JOIN leasing_companies lc ON lc.company_id = cm.company_id;",
            "",
            "-- Empty groups first; aggregates and selected_companies are filled later.",
            "INSERT INTO application_groups (",
            "    user_id, vehicles_count, selected_companies, total_vehicles_price, created_at, updated_at",
            ")",
            "SELECT",
            "    um.user_id,",
            "    0,",
            "    '[]'::jsonb,",
            "    0,",
            "    sg.created_at,",
            "    sg.created_at",
            "FROM seed_groups sg",
            "JOIN seed_client_user_map um ON um.client_key = sg.client_key",
            "WHERE NOT EXISTS (",
            "    SELECT 1",
            "    FROM application_groups ag",
            "    WHERE ag.user_id = um.user_id",
            "      AND ag.created_at IS NOT DISTINCT FROM sg.created_at",
            ");",
            "",
            "CREATE TEMP TABLE seed_group_map ON COMMIT DROP AS",
            "SELECT",
            "    sg.group_key,",
            "    ag.id AS group_id",
            "FROM seed_groups sg",
            "JOIN seed_client_user_map um ON um.client_key = sg.client_key",
            "JOIN application_groups ag",
            "    ON ag.user_id = um.user_id",
            "   AND ag.created_at IS NOT DISTINCT FROM sg.created_at;",
            "",
            "-- Applications",
            "INSERT INTO leasing_applications (",
            "    total_amount, down_payment, down_payment_percent, lease_term_months, monthly_payment,",
            "    total_cost, markup, rate, total_interest, buyout_amount, vat_refund,",
            "    profit_tax_savings, total_savings, selected_leasing_companies,",
            "    questionnaire_completed, questionnaire_progress, current_stage, created_at, updated_at",
            ")",
            "SELECT",
            "    cm.company_id,",
            "    NULL,",
            "    sa.name,",
            "    sa.email,",
            "    sa.company_name_or_inn,",
            "    sa.status,",
            "    sa.total_amount,",
            "    sa.down_payment,",
            "    sa.down_payment_percent,",
            "    sa.lease_term_months,",
            "    sa.monthly_payment,",
            "    sa.total_cost,",
            "    sa.markup,",
            "    sa.rate,",
            "    sa.total_interest,",
            "    sa.buyout_amount,",
            "    sa.vat_refund,",
            "    sa.profit_tax_savings,",
            "    sa.total_savings,",
            "    (",
            "        SELECT coalesce(array_agg(lm.leasing_company_id ORDER BY lm.leasing_company_id), ARRAY[]::int[])",
            "        FROM unnest(string_to_array(sa.leasing_company_keys_csv, ',')) AS key_item(lc_key)",
            "        JOIN seed_lc_map lm ON lm.lc_key = btrim(key_item.lc_key)",
            "    ),",
            "    sa.questionnaire_completed,",
            "    sa.questionnaire_progress,",
            "    sa.current_stage,",
            "    sa.created_at,",
            "    sa.updated_at",
            "FROM seed_applications sa",
            "JOIN seed_client_company_map cm ON cm.client_key = sa.client_key",
            "WHERE NOT EXISTS (",
            "    SELECT 1",
            "    FROM leasing_applications la",
            "    WHERE la.company_id = cm.company_id",
            "      AND la.name = sa.name",
            "      AND la.created_at IS NOT DISTINCT FROM sa.created_at",
            ");",
            "",
            "UPDATE leasing_applications la",
            "SET",
            "    email = sa.email,",
            "    company_name_or_inn = sa.company_name_or_inn,",
            "    status = sa.status,",
            "    total_amount = sa.total_amount,",
            "    down_payment = sa.down_payment,",
            "    down_payment_percent = sa.down_payment_percent,",
            "    lease_term_months = sa.lease_term_months,",
            "    monthly_payment = sa.monthly_payment,",
            "    total_cost = sa.total_cost,",
            "    markup = sa.markup,",
            "    rate = sa.rate,",
            "    total_interest = sa.total_interest,",
            "    buyout_amount = sa.buyout_amount,",
            "    vat_refund = sa.vat_refund,",
            "    profit_tax_savings = sa.profit_tax_savings,",
            "    total_savings = sa.total_savings,",
            "    selected_leasing_companies = (",
            "        SELECT coalesce(array_agg(lm.leasing_company_id ORDER BY lm.leasing_company_id), ARRAY[]::int[])",
            "        FROM unnest(string_to_array(sa.leasing_company_keys_csv, ',')) AS key_item(lc_key)",
            "        JOIN seed_lc_map lm ON lm.lc_key = btrim(key_item.lc_key)",
            "    ),",
            "    questionnaire_completed = sa.questionnaire_completed,",
            "    questionnaire_progress = sa.questionnaire_progress,",
            "    current_stage = sa.current_stage,",
            "    updated_at = sa.updated_at",
            "FROM seed_applications sa",
            "JOIN seed_client_company_map cm ON cm.client_key = sa.client_key",
            "WHERE la.company_id = cm.company_id",
            "  AND la.name = sa.name",
            "  AND la.created_at IS NOT DISTINCT FROM sa.created_at;",
            "",
            "CREATE TEMP TABLE seed_application_map ON COMMIT DROP AS",
            "SELECT",
            "    sa.application_key,",
            "    la.id AS application_id,",
            "    sa.group_key,",
            "    sa.lc_link_status,",
            "    sa.leasing_company_keys_csv",
            "FROM seed_applications sa",
            "JOIN seed_client_company_map cm ON cm.client_key = sa.client_key",
            "JOIN leasing_applications la",
            "    ON la.company_id = cm.company_id",
            "   AND la.name = sa.name",
            "   AND la.created_at IS NOT DISTINCT FROM sa.created_at;",
            "",
            "-- Group links",
            "INSERT INTO leasing_applications_groups (application_id, group_id)",
            "SELECT",
            "    am.application_id,",
            "    gm.group_id",
            "FROM seed_application_map am",
            "JOIN seed_group_map gm ON gm.group_key = am.group_key",
            "WHERE TRUE",
            "ON CONFLICT DO NOTHING;",
            "",
            "-- Vehicle rows",
            "INSERT INTO application_vehicles (",
            "    application_id, vehicle_id, modification_id, quantity, unit_price, total_price, comment, is_model_order",
            ")",
            "SELECT",
            "    am.application_id,",
            "    sv.vehicle_id,",
            "    sv.modification_id,",
            "    sv.quantity,",
            "    sv.unit_price,",
            "    sv.total_price,",
            "    sv.comment,",
            "    sv.is_model_order",
            "FROM seed_vehicles sv",
            "JOIN seed_application_map am ON am.application_key = sv.application_key",
            "WHERE NOT EXISTS (",
            "    SELECT 1",
            "    FROM application_vehicles av",
            "    WHERE av.application_id = am.application_id",
            "      AND av.vehicle_id IS NOT DISTINCT FROM sv.vehicle_id",
            "      AND av.modification_id IS NOT DISTINCT FROM sv.modification_id",
            ");",
            "",
            "-- LC links",
            "INSERT INTO leasing_company_applications (",
            "    application_id, leasing_company_id, status, review_notes, submitted_at",
            ")",
            "SELECT",
            "    am.application_id,",
            "    lm.leasing_company_id,",
            "    am.lc_link_status::leasing_company_application_status,",
            "    'generated from workbook',",
            "    CASE",
            "        WHEN am.lc_link_status IN ('approved', 'rejected', 'closed', 'issued') THEN CURRENT_TIMESTAMP",
            "        ELSE NULL",
            "    END",
            "FROM seed_application_map am",
            "JOIN LATERAL unnest(string_to_array(am.leasing_company_keys_csv, ',')) AS key_item(lc_key) ON TRUE",
            "JOIN seed_lc_map lm ON lm.lc_key = btrim(key_item.lc_key)",
            "WHERE NOT EXISTS (",
            "    SELECT 1",
            "    FROM leasing_company_applications lca",
            "    WHERE lca.application_id = am.application_id",
            "      AND lca.leasing_company_id = lm.leasing_company_id",
            ");",
            "",
            "UPDATE leasing_company_applications lca",
            "SET",
            "    status = am.lc_link_status::leasing_company_application_status,",
            "    submitted_at = CASE",
            "        WHEN am.lc_link_status IN ('approved', 'rejected', 'closed', 'issued') THEN coalesce(lca.submitted_at, CURRENT_TIMESTAMP)",
            "        WHEN am.lc_link_status = 'prescoring' THEN NULL",
            "        ELSE lca.submitted_at",
            "    END,",
            "    review_notes = coalesce(lca.review_notes, 'generated from workbook'),",
            "    updated_at = CURRENT_TIMESTAMP",
            "FROM seed_application_map am",
            "JOIN LATERAL unnest(string_to_array(am.leasing_company_keys_csv, ',')) AS key_item(lc_key) ON TRUE",
            "JOIN seed_lc_map lm ON lm.lc_key = btrim(key_item.lc_key)",
            "WHERE lca.application_id = am.application_id",
            "  AND lca.leasing_company_id = lm.leasing_company_id;",
            "",
            "-- Proposals for statuses introduced by the current LC workflow.",
            "INSERT INTO leasing_proposals (",
            "    leasing_company_application_id, kind, position,",
            "    total_amount, down_payment, down_payment_percent, lease_term_months,",
            "    monthly_payment, total_cost, markup, rate, total_interest, buyout_amount,",
            "    vat_refund, profit_tax_savings, total_savings,",
            "    client_decision_action, client_decision_at",
            ")",
            "SELECT",
            "    lca.id,",
            "    CASE WHEN lca.status = 'prescoring' THEN 'preliminary'::leasing_proposal_kind ELSE 'final'::leasing_proposal_kind END,",
            "    1,",
            "    sa.total_amount,",
            "    sa.down_payment,",
            "    sa.down_payment_percent,",
            "    sa.lease_term_months,",
            "    sa.monthly_payment,",
            "    sa.total_cost,",
            "    sa.markup,",
            "    sa.rate,",
            "    sa.total_interest,",
            "    coalesce(sa.buyout_amount, 0),",
            "    sa.vat_refund,",
            "    sa.profit_tax_savings,",
            "    sa.total_savings,",
            "    CASE WHEN lca.status = 'issued' THEN 'accepted' ELSE NULL END,",
            "    CASE WHEN lca.status = 'issued' THEN CURRENT_TIMESTAMP ELSE NULL END",
            "FROM seed_application_map am",
            "JOIN seed_applications sa ON sa.application_key = am.application_key",
            "JOIN LATERAL unnest(string_to_array(am.leasing_company_keys_csv, ',')) AS key_item(lc_key) ON TRUE",
            "JOIN seed_lc_map lm ON lm.lc_key = btrim(key_item.lc_key)",
            "JOIN leasing_company_applications lca ON lca.application_id = am.application_id",
            "    AND lca.leasing_company_id = lm.leasing_company_id",
            "WHERE lca.status IN ('prescoring', 'approved', 'issued')",
            "ON CONFLICT ON CONSTRAINT uq_leasing_proposals_lca_kind DO UPDATE SET",
            "    position = EXCLUDED.position,",
            "    total_amount = EXCLUDED.total_amount,",
            "    down_payment = EXCLUDED.down_payment,",
            "    down_payment_percent = EXCLUDED.down_payment_percent,",
            "    lease_term_months = EXCLUDED.lease_term_months,",
            "    monthly_payment = EXCLUDED.monthly_payment,",
            "    total_cost = EXCLUDED.total_cost,",
            "    markup = EXCLUDED.markup,",
            "    rate = EXCLUDED.rate,",
            "    total_interest = EXCLUDED.total_interest,",
            "    buyout_amount = EXCLUDED.buyout_amount,",
            "    vat_refund = EXCLUDED.vat_refund,",
            "    profit_tax_savings = EXCLUDED.profit_tax_savings,",
            "    total_savings = EXCLUDED.total_savings,",
            "    client_decision_action = coalesce(leasing_proposals.client_decision_action, EXCLUDED.client_decision_action),",
            "    client_decision_at = coalesce(leasing_proposals.client_decision_at, EXCLUDED.client_decision_at),",
            "    updated_at = CURRENT_TIMESTAMP;",
            "",
            "-- Group aggregates",
            "UPDATE application_groups ag",
            "SET",
            "    vehicles_count = agg.vehicles_count,",
            "    total_vehicles_price = agg.total_vehicles_price,",
            "    selected_companies = agg.selected_companies,",
            "    updated_at = CURRENT_TIMESTAMP",
            "FROM (",
            "    SELECT",
            "        gm.group_id,",
            "        coalesce(sum(av.quantity), 0)::int AS vehicles_count,",
            "        coalesce(sum(av.total_price), 0)::numeric(15,2) AS total_vehicles_price,",
            "        coalesce(",
            "            jsonb_agg(DISTINCT jsonb_build_object(",
            "                'company_id', lm.leasing_company_id,",
            "                'company_name', lm.company_name",
            "            )) FILTER (WHERE lm.leasing_company_id IS NOT NULL),",
            "            '[]'::jsonb",
            "        ) AS selected_companies",
            "    FROM seed_group_map gm",
            "    JOIN leasing_applications_groups lag ON lag.group_id = gm.group_id",
            "    LEFT JOIN application_vehicles av ON av.application_id = lag.application_id",
            "    LEFT JOIN leasing_company_applications lca ON lca.application_id = lag.application_id",
            "    LEFT JOIN seed_lc_map lm ON lm.leasing_company_id = lca.leasing_company_id",
            "    GROUP BY gm.group_id",
            ") AS agg",
            "WHERE ag.id = agg.group_id;",
            "",
            "COMMIT;",
            "",
            "-- Quick checks:",
            "-- SELECT count(*) FROM leasing_applications;",
            "-- SELECT count(*) FROM application_groups;",
            "-- SELECT count(*) FROM leasing_applications_groups;",
            "-- SELECT count(*) FROM application_vehicles;",
            "-- SELECT count(*) FROM leasing_company_applications;",
        ]
    )


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "seed_leasing_workbook"


def _discover_revision_defaults(versions_dir: Path) -> tuple[str, str]:
    max_revision = 0
    for path in versions_dir.glob("[0-9][0-9][0-9]_*.py"):
        match = re.match(r"^(\d{3})_", path.name)
        if match:
            max_revision = max(max_revision, int(match.group(1)))
    if max_revision == 0:
        raise ValueError(f"No numeric Alembic revisions found in {versions_dir}")
    return f"{max_revision + 1:03d}", f"{max_revision:03d}"


def create_seed_migration(
    *,
    workbook_path: Path,
    versions_dir: Path,
    revision: str | None,
    down_revision: str | None,
    message: str,
    slug: str | None,
    script_sql_output: Path | None,
    force: bool,
) -> tuple[Path, Path, Path | None]:
    versions_dir.mkdir(parents=True, exist_ok=True)
    default_revision, default_down_revision = _discover_revision_defaults(versions_dir)
    revision = revision or default_revision
    down_revision = down_revision or default_down_revision
    slug = _slugify(slug or message)

    py_path = versions_dir / f"{revision}_{slug}.py"
    sql_path = versions_dir / f"{revision}_{slug}.sql"
    if not force:
        existing = [path for path in (py_path, sql_path) if path.exists()]
        if existing:
            names = ", ".join(str(path) for path in existing)
            raise ValueError(f"Refusing to overwrite existing files: {names}")

    sql = generate_sql(workbook_path)
    sql_path.write_text(sql, encoding="utf-8")

    py_source = MIGRATION_TEMPLATE.format(
        message=message,
        workbook_path=workbook_path,
        revision=revision,
        down_revision=down_revision,
        sql_filename=sql_path.name,
    )
    py_path.write_text(py_source, encoding="utf-8")

    copied_sql_path: Path | None = None
    if script_sql_output is not None:
        script_sql_output.parent.mkdir(parents=True, exist_ok=True)
        script_sql_output.write_text(sql, encoding="utf-8")
        copied_sql_path = script_sql_output

    return py_path, sql_path, copied_sql_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an xlsx template and generate SQL for leasing seed data."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    template_parser = subparsers.add_parser("template", help="Create workbook template")
    template_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Where to write the .xlsx template",
    )

    sql_parser = subparsers.add_parser("sql", help="Generate SQL from workbook")
    sql_parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to filled .xlsx workbook",
    )
    sql_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Where to write generated .sql",
    )

    migration_parser = subparsers.add_parser(
        "migration",
        help="Generate SQL plus an Alembic seed migration from a filled workbook",
    )
    migration_parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to filled .xlsx workbook",
    )
    migration_parser.add_argument(
        "--versions-dir",
        type=Path,
        default=Path("alembic/versions"),
        help="Alembic versions directory",
    )
    migration_parser.add_argument(
        "--revision",
        default=None,
        help="Revision id. Defaults to next numeric revision, e.g. 018",
    )
    migration_parser.add_argument(
        "--down-revision",
        default=None,
        help="Down revision. Defaults to current highest numeric revision",
    )
    migration_parser.add_argument(
        "--message",
        default="Seed leasing workbook data",
        help="Migration docstring/message",
    )
    migration_parser.add_argument(
        "--slug",
        default=None,
        help="Filename slug. Defaults to a slugified message",
    )
    migration_parser.add_argument(
        "--script-sql-output",
        type=Path,
        default=None,
        help="Optional extra copy of the generated SQL, e.g. scripts/seed.sql",
    )
    migration_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite generated migration files if they already exist",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "template":
            create_template(args.output)
            _stderr(f"Template written to {args.output}")
            return 0

        if args.command == "sql":
            sql = generate_sql(args.input)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(sql, encoding="utf-8")
            _stderr(f"SQL written to {args.output}")
            return 0

        py_path, sql_path, copied_sql_path = create_seed_migration(
            workbook_path=args.input,
            versions_dir=args.versions_dir,
            revision=args.revision,
            down_revision=args.down_revision,
            message=args.message,
            slug=args.slug,
            script_sql_output=args.script_sql_output,
            force=args.force,
        )
        _stderr(f"Migration written to {py_path}")
        _stderr(f"Companion SQL written to {sql_path}")
        if copied_sql_path is not None:
            _stderr(f"SQL copy written to {copied_sql_path}")
        return 0
    except Exception as exc:
        _stderr(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

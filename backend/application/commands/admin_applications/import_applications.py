"""Bulk import LCA rows from CSV (admin)."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, NoReturn
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.dwh_enrichment import build_lca_payload
from infrastructure.messaging.topics import LCA_CHANGED, LCA_SNAPSHOT
from infrastructure.repositories import (
    application_repository as app_repo,
)
from infrastructure.repositories import (
    company_repository as company_repo,
)
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.repositories import status_history_repository as hist_repo

# ---------------------------------------------------------------------------
# Command / result
# ---------------------------------------------------------------------------

@dataclass
class ImportApplicationsCommand:
    csv_bytes: bytes


@dataclass
class ImportApplicationsResult:
    created: int
    updated: int
    errors: list[str]
    message: str
    # The transaction owner publishes these payloads only after committing.
    dwh_payloads: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


@dataclass
class ImportApplicationRowResult:
    action: str
    error: str | None = None
    dwh_payloads: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


class _RowLogicalError(Exception):
    """Internal signal to roll back the current row savepoint."""


def _raise_row_logical_error(message: str) -> NoReturn:
    raise _RowLogicalError(message)


# ---------------------------------------------------------------------------
# Row parsing
# ---------------------------------------------------------------------------

def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip().replace(" ", "")
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_decimal(value: str | None) -> Decimal | None:
    """Parse a decimal tolerant of comma decimal separators and spaces."""
    if value is None:
        return None
    text = value.strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


# Optional financial / vehicle columns forwarded from CSV into the parent
# leasing_applications row (and from there denormalized into the DWH).
_DECIMAL_FIELDS: tuple[str, ...] = (
    "total_amount",
    "down_payment",
    "down_payment_percent",
    "monthly_payment",
    "total_cost",
    "markup",
    "rate",
    "total_interest",
    "buyout_amount",
    "vat_refund",
    "profit_tax_savings",
    "total_savings",
)


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"", "0", "false", "no", "нет"}


def _parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value.strip())
    except ValueError:
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    try:
        return datetime.fromisoformat(text).replace(tzinfo=UTC)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Upsert logic
# ---------------------------------------------------------------------------

def _parse_row(
    row: dict[str, str],
) -> tuple[UUID, UUID, UUID | None, str, datetime] | str:
    """Validate and parse the CSV row."""
    application_id = _parse_uuid(row.get("application_id"))
    leasing_company_id = _parse_uuid(row.get("leasing_company_id"))
    lca_id_raw = _parse_uuid(row.get("id"))
    status = (row.get("status") or "").strip()
    created_at = _parse_datetime(row.get("created_at")) or datetime.now(UTC)

    if application_id is None:
        return "пропущено обязательное поле application_id"
    if leasing_company_id is None:
        return "пропущено обязательное поле leasing_company_id"
    if not status:
        return "пропущено обязательное поле status"
    return (application_id, leasing_company_id, lca_id_raw, status, created_at)


async def _resolve_lc_id(
    session: AsyncSession,
    leasing_company_id: UUID,
) -> tuple[UUID | None, str | None]:
    lc_extension = await company_repo.get_leasing_company_extension(
        session, leasing_company_id
    )
    if lc_extension is None:
        return (
            None,
            f"лизинговая компания c company_id={leasing_company_id} не найдена в таблице leasing_companies",
        )
    return lc_extension["id"], None


async def _ensure_parent_application(
    session: AsyncSession,
    application_id: UUID,
    row: dict[str, str],
    leasing_company_id: UUID,
) -> tuple[dict[str, Any] | None, str | None]:
    parent = await app_repo.get_by_id(session, application_id)
    if parent is not None:
        return parent, None

    company_id = _parse_uuid(row.get("company_id")) or leasing_company_id
    if company_id is None:
        return None, "родительская заявка не найдена, и company_id не указан в CSV"

    company = await company_repo.get_company_by_id(session, company_id)
    if company is None:
        return None, f"компания {company_id} не найдена в таблице companies"

    display_number = (
        row.get("display_number") or f"IMP-{application_id.hex[:8].upper()}"
    ).strip()
    dealer_company_id = _parse_uuid(row.get("dealer_company_id"))
    payload: dict[str, Any] = {
        "id": application_id,
        "display_number": display_number,
        "company_id": company_id,
        "dealer_company_id": dealer_company_id,
        "name": row.get("name", "").strip() or None,
        "email": row.get("email", "").strip() or None,
    }
    # Optional financial / vehicle columns (create_application filters unknown
    # keys, but we only emit real leasing_applications columns).
    vehicle_id = _parse_uuid(row.get("vehicle_id"))
    if vehicle_id is not None:
        payload["vehicle_id"] = vehicle_id
    lease_term_months = _parse_int(row.get("lease_term_months"))
    if lease_term_months is not None:
        payload["lease_term_months"] = lease_term_months
    for field_name in _DECIMAL_FIELDS:
        parsed = _parse_decimal(row.get(field_name))
        if parsed is not None:
            payload[field_name] = parsed
    await app_repo.create_application(session, payload=payload)
    parent = await app_repo.get_by_id(session, application_id)
    if parent is None:
        return None, f"не удалось создать родительскую заявку {application_id}"
    return parent, None


async def _ensure_application_vehicle(
    session: AsyncSession,
    application_id: UUID,
    row: dict[str, str],
) -> str | None:
    """Idempotently create an ``application_vehicles`` row from CSV columns.

    No-op when neither ``vehicle_id`` nor ``modification_id`` is present, and
    when a matching row already exists for this application.
    """
    vehicle_id = _parse_uuid(row.get("vehicle_id"))
    modification_id = (row.get("modification_id") or "").strip() or None
    if vehicle_id is None and modification_id is None:
        return None

    quantity = _parse_int(row.get("quantity")) or 1
    unit_price = _parse_decimal(row.get("unit_price")) or _parse_decimal(
        row.get("total_amount")
    )
    total_price = _parse_decimal(row.get("total_price")) or _parse_decimal(
        row.get("total_amount")
    )
    if unit_price is None or total_price is None:
        return "vehicle row requires unit_price/total_price or total_amount"

    existing = await app_repo.list_application_vehicles(session, application_id)
    for item in existing:
        if (
            str(item.get("vehicle_id") or "") == str(vehicle_id or "")
            and (item.get("modification_id") or None) == modification_id
        ):
            return None

    await app_repo.create_application_vehicle(
        session,
        application_id=application_id,
        vehicle_id=vehicle_id,
        modification_id=modification_id,
        quantity=quantity,
        unit_price=unit_price,
        total_price=total_price,
        is_model_order=_parse_bool(
            row.get("is_model_order"), default=vehicle_id is None
        ),
        comment=(row.get("comment") or "").strip() or None,
    )
    return None


async def _upsert_link(
    session: AsyncSession,
    application_id: UUID,
    leasing_company_id: UUID,
    status: str,
    created_at: datetime,
    lca_id_raw: UUID | None,
) -> tuple[UUID, str]:
    existing_link = None
    if lca_id_raw is not None:
        existing_link = await lca_repo.get_link_by_id(session, lca_id_raw)
    if existing_link is None:
        existing_link = await lca_repo.get_link_for_app_and_lc(
            session,
            application_id=application_id,
            leasing_company_id=leasing_company_id,
        )
    if existing_link is not None:
        old_status = str(existing_link.get("status") or "")
        if old_status != status:
            await lca_repo.update_link_status(
                session,
                link_id=existing_link["id"],
                new_status=status,
            )
            await hist_repo.append_lca_status_history(
                session,
                lca_id=existing_link["id"],
                application_id=application_id,
                old_status=old_status or None,
                new_status=status,
                reason="Импорт заявок",
            )
        return existing_link["id"], "updated"

    lca_id = await lca_repo.create_link(
        session,
        application_id=application_id,
        leasing_company_id=leasing_company_id,
        status=status,
        created_at=created_at,
    )
    return lca_id, "created"


async def _build_lca_dwh_payload(
    session: AsyncSession,
    lca_id: UUID,
    row: dict[str, str],
    parent: dict[str, Any],
) -> dict[str, Any] | None:
    """Build an LCA event payload without publishing it.

    Builds the payload with ``build_lca_dwh_payload`` (financial + meta fields
    from the parent application) then enriches it via
    ``dwh_enrichment.build_lca_payload`` so dealer_name/dealer_city,
    leasing_company_name and vehicle mark/model are populated — identical to
    the consumer's expectations.
    """
    lca_dict = await lca_repo.get_link_by_id(session, lca_id)
    if lca_dict is None:
        return None

    # Resolve distributor_id from CSV or via the dealer company extension so the
    # canonical builder can denormalize it onto the row.
    app_data = dict(parent)
    dealer_cid = app_data.get("dealer_company_id")
    distributor_id = _parse_uuid(row.get("distributor_id"))
    if distributor_id is None and dealer_cid:
        distributor = await company_repo.get_distributor_extension(session, dealer_cid)
        distributor_id = distributor["id"] if distributor else None
    app_data["distributor_id"] = distributor_id

    return await build_lca_payload(session, lca_dict, app_data)


async def _upsert_lca_row(
    session: AsyncSession,
    row: dict[str, str],
) -> ImportApplicationRowResult:
    parsed = _parse_row(row)
    if isinstance(parsed, str):
        return ImportApplicationRowResult("error", parsed)
    application_id, leasing_company_id, lca_id_raw, status, created_at = parsed

    lc_id, err = await _resolve_lc_id(session, leasing_company_id)
    if err:
        return ImportApplicationRowResult("error", err)
    assert lc_id is not None
    leasing_company_id = lc_id

    parent, err = await _ensure_parent_application(
        session, application_id, row, leasing_company_id
    )
    if err:
        return ImportApplicationRowResult("error", err)

    err = await _ensure_application_vehicle(session, application_id, row)
    if err:
        return ImportApplicationRowResult("error", err)

    lca_id, action = await _upsert_link(
        session, application_id, leasing_company_id, status, created_at, lca_id_raw
    )

    dwh_payloads: dict[str, list[dict[str, Any]]] = {}
    if parent is not None:
        payload = await _build_lca_dwh_payload(session, lca_id, row, parent)
        if payload is not None:
            dwh_payloads = {
                LCA_SNAPSHOT: [payload],
                LCA_CHANGED: [payload],
            }

    return ImportApplicationRowResult(action, dwh_payloads=dwh_payloads)


async def handle_import_applications(
    cmd: ImportApplicationsCommand, session: AsyncSession
) -> ImportApplicationsResult:
    text = cmd.csv_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")

    created = 0
    updated = 0
    errors: list[str] = []
    dwh_payloads: dict[str, list[dict[str, Any]]] = {}

    for idx, row in enumerate(reader, start=1):
        try:
            async with session.begin_nested():
                row_result = await _upsert_lca_row(
                    session,
                    row,
                )
                if row_result.action == "error":
                    _raise_row_logical_error(
                        row_result.error or "неизвестная ошибка импорта"
                    )
        except _RowLogicalError as exc:
            errors.append(f"Строка {idx}: {exc}")
            continue
        except Exception as exc:
            errors.append(f"Строка {idx}: {exc}")
            continue
        if row_result.action == "created":
            created += 1
        elif row_result.action == "updated":
            updated += 1
        for topic, payloads in row_result.dwh_payloads.items():
            dwh_payloads.setdefault(topic, []).extend(payloads)

    parts = [f"Создано {created}", f"Обновлено {updated}"]
    message = ", ".join(parts)
    if errors:
        message += f", ошибок: {len(errors)}"
    return ImportApplicationsResult(
        created=created,
        updated=updated,
        errors=errors,
        message=message,
        dwh_payloads=dwh_payloads,
    )

"""List application vehicles (admin scope) query."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import ApplicationNotFoundError
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import support_repository


@dataclass
class ListAdminApplicationVehiclesQuery:
    application_id: uuid.UUID


async def handle_list_admin_application_vehicles(
    query: ListAdminApplicationVehiclesQuery, session: AsyncSession
) -> dict[str, Any]:
    application = await app_repo.get_by_id(session, query.application_id)
    if application is None:
        raise ApplicationNotFoundError(query.application_id)
    vehicles = await app_repo.list_application_vehicles_with_catalog(
        session, query.application_id
    )
    # Remap catalog field names to the frontend AdminVehicle shape.
    for v in vehicles:
        if "vehicle_year" in v:
            v["year"] = v["vehicle_year"]
        if "mark_cyrillic_name" in v:
            v["mark_cyrillic"] = v.pop("mark_cyrillic_name")
        if "model_cyrillic_name" in v:
            v["model_cyrillic"] = v.pop("model_cyrillic_name")
        if "group_name" in v:
            v["complectation_name"] = v["group_name"]
    calculation = await app_repo.get_calculation(session, query.application_id)
    program_names = await _support_program_names(session, calculation)
    _attach_support_summary(vehicles, calculation, program_names)
    return {"vehicles": vehicles}


def _attach_support_summary(
    vehicles: list[dict[str, Any]],
    calculation: dict[str, Any] | None,
    program_names: dict[str, str],
) -> None:
    if not vehicles or not calculation:
        return
    support_by_vehicle = _support_by_vehicle(calculation, program_names)
    if not support_by_vehicle:
        return

    for vehicle in vehicles:
        vehicle_id = _as_key(vehicle.get("vehicle_id"))
        if vehicle_id is None:
            continue
        support = support_by_vehicle.get(vehicle_id)
        if support is None:
            continue
        vehicle.update(support)


def _support_by_vehicle(
    calculation: dict[str, Any],
    program_names: dict[str, str],
) -> dict[str, dict[str, Any]]:
    details = _support_details_by_id(calculation)
    result: dict[str, dict[str, Any]] = {}
    rows = calculation.get("support_per_vehicle")
    if not isinstance(rows, list):
        return result

    for row in rows:
        if not isinstance(row, dict):
            continue
        vehicle_id = _as_key(row.get("vehicle_id"))
        if vehicle_id is None:
            continue
        applied = [
            support
            for support in row.get("applied_supports") or []
            if isinstance(support, dict) and float(support.get("amount") or 0) > 0
        ]
        if not applied:
            continue

        first = applied[0]
        support_program_ids = [
            str(support.get("support_program_id"))
            for support in applied
            if support.get("support_program_id") is not None
        ]
        matched_details = [
            detail
            for program_id in support_program_ids
            if (detail := details.get(program_id)) is not None
        ]
        names = [
            str(detail.get("name"))
            for detail in matched_details
            if detail.get("name")
        ]
        if not names:
            names = [
                program_names[program_id]
                for program_id in support_program_ids
                if program_id in program_names
            ]
        first_bol = next(
            (
                detail.get("bill_of_lading")
                for detail in matched_details
                if detail.get("bill_of_lading")
            ),
            None,
        )

        result[vehicle_id] = {
            "support_type": first.get("type"),
            "support_amount": sum(float(support.get("amount") or 0) for support in applied),
            "support_program_id": support_program_ids[0] if support_program_ids else None,
            "support_program_ids": support_program_ids,
            "applied_supports": applied,
            "support_program_info": {
                "name": ", ".join(names) if names else None,
                "bill_of_lading": first_bol,
            },
        }
    return result


async def _support_program_names(
    session: AsyncSession,
    calculation: dict[str, Any] | None,
) -> dict[str, str]:
    if not calculation:
        return {}
    program_ids = _support_program_ids(calculation)
    result: dict[str, str] = {}
    for program_id in program_ids:
        try:
            parsed = uuid.UUID(program_id)
        except (TypeError, ValueError):
            continue
        program = await support_repository.get_program_by_id(session, parsed)
        if program and program.get("name"):
            result[program_id] = str(program["name"])
    return result


def _support_program_ids(calculation: dict[str, Any]) -> list[str]:
    result: list[str] = []
    rows = calculation.get("support_per_vehicle")
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, dict):
            continue
        for support in row.get("applied_supports") or []:
            if not isinstance(support, dict):
                continue
            program_id = support.get("support_program_id")
            if program_id is None:
                continue
            text = str(program_id)
            if text not in result:
                result.append(text)
    return result


def _support_details_by_id(
    calculation: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    details = calculation.get("support_program_details")
    if not isinstance(details, list):
        return result
    for detail in details:
        if not isinstance(detail, dict):
            continue
        detail_id = detail.get("id")
        if detail_id is None:
            continue
        result[str(detail_id)] = detail
    return result


def _as_key(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)

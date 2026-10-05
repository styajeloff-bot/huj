"""Shared SQL predicates for application origin and number search."""

from typing import Any

import sqlalchemy as sa

from domain.application_sources import parse_application_number_search
from infrastructure.models.applications import LeasingApplication


def application_source_filters(
    *, source_types: tuple[str, ...] = (), search: str | None = None
) -> list[Any]:
    conditions: list[Any] = []
    if source_types:
        conditions.append(LeasingApplication.source_type.in_(source_types))
    if not search or not search.strip():
        return conditions
    number, source, digits = parse_application_number_search(search)
    if source:
        conditions.append(LeasingApplication.source_type == source)
        # A prefix is a number query, never an alternative name/email lookup.
        if not number:
            conditions.append(sa.false())
            return conditions
    pattern = f"%{number}%"
    number_checks = [LeasingApplication.display_number.ilike(pattern)]
    if digits:
        normalized_number = sa.func.regexp_replace(
            LeasingApplication.display_number, "[^0-9]", "", "g"
        )
        number_checks.append(normalized_number.like(f"%{digits}%"))
    if source is None:
        number_checks.extend([
            LeasingApplication.name.ilike(pattern),
            LeasingApplication.email.ilike(pattern),
            sa.cast(LeasingApplication.id, sa.String).ilike(pattern),
        ])
    conditions.append(sa.or_(*number_checks))
    return conditions

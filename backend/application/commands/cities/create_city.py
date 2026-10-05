"""Create city command."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.city import City
from domain.errors import CityAlreadyExistsError
from infrastructure.repositories import city_repository as repo


@dataclass
class CreateCityCommand:
    name: str


async def handle_create_city(
    cmd: CreateCityCommand, session: AsyncSession
) -> dict[str, Any]:
    city = City(city_id=None, name=cmd.name)
    city.ensure_valid()
    if await repo.name_exists(session, city.name):
        raise CityAlreadyExistsError(city.name)
    return cast("dict[str, Any]", await repo.create_city(session, name=city.name))

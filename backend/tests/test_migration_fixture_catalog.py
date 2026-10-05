"""Metadata test fixtures retain lookup rows seeded by deployed migrations."""

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


async def test_metadata_fixture_seeds_the_migrated_car_status_catalog(
    db_session: AsyncSession,
) -> None:
    rows = (
        await db_session.execute(
            sa.text("SELECT status_name, status_display_name FROM cars_status")
        )
    ).all()
    assert {row.status_name: row.status_display_name for row in rows} == {
        "confirmed": "Подтверждено",
        "not_confirmed": "Не подтверждено",
        "active": "Подтверждается",
        "replacement": "Замена ТС",
    }

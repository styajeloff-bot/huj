"""Functional tests for client handlers (real Postgres, no HTTP)."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.client import (
    AddFavoriteCommand,
    BulkRemoveFavoritesCommand,
    DeleteSavedCalculationCommand,
    RemoveFavoriteCommand,
    RequestPhoneChangeCommand,
    SaveCalculationCommand,
    UpdateClientProfileCommand,
    VerifyPhoneChangeCommand,
    handle_add_favorite,
    handle_bulk_remove_favorites,
    handle_delete_saved_calculation,
    handle_remove_favorite,
    handle_request_phone_change,
    handle_save_calculation,
    handle_update_client_profile,
    handle_verify_phone_change,
)
from application.queries.client import (
    GetClientProfileQuery,
    ListFavoritesQuery,
    ListSavedCalculationsQuery,
    handle_get_client_profile,
    handle_list_favorites,
    handle_list_saved_calculations,
)
from domain.errors import (
    AccessDeniedError,
    FavoriteAlreadyExistsError,
    InvalidPhoneChangeError,
    PhoneAlreadyInUseError,
    SavedCalculationNotFoundError,
    UserNotFoundError,
)
from infrastructure.models.users import User, UserFavorite, VerificationCode
from infrastructure.repositories import (
    user_identity_verification_repository as verifications,
)
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_vehicle(db: AsyncSession) -> Vehicle:
    v = Vehicle(status="available", is_available=True)
    db.add(v)
    await db.flush()
    await db.refresh(v)
    return v


async def _mark_mobile_id_verified(
    db_session: AsyncSession, user: User, *, birthdate: date = date(1991, 1, 8)
) -> dict[str, Any]:
    attempt = await verifications.create_attempt(
        db_session,
        user_id=user.id,
        provider=verifications.PROVIDER_MOBILE_ID,
        phone_number=user.phone,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        birthdate=birthdate,
    )
    verified = await verifications.mark_verified(
        db_session,
        verification_id=attempt["id"],
        mobile_id_sub=f"sub-{attempt['id']}",
        phone_number=user.phone,
        birthdate=birthdate,
        birthdate_match="Y",
        given_name="Алена",
        middle_name="Леонтьевна",
        family_name="Даурова",
    )
    assert verified is not None
    return cast("dict[str, Any]", verified)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


async def test_get_profile_returns_user_with_null_profile_fields(
    db_session: AsyncSession, client_user: User
) -> None:
    result = await handle_get_client_profile(
        GetClientProfileQuery(user_id=client_user.id), db_session
    )
    assert result["user_id"] == client_user.id
    assert result["phone"] == client_user.phone
    assert result["profile_id"] is None
    assert result["client_type"] is None


async def test_get_profile_404_for_unknown_user(db_session: AsyncSession) -> None:
    with pytest.raises(UserNotFoundError):
        await handle_get_client_profile(
            GetClientProfileQuery(user_id=uuid4()), db_session
        )


async def test_update_profile_updates_user_basic_fields(
    db_session: AsyncSession, client_user: User
) -> None:
    updated = await handle_update_client_profile(
        UpdateClientProfileCommand(
            user_id=client_user.id,
            data={"name": "Новое Имя", "email": "new@test.local"},
        ),
        db_session,
    )
    assert updated["name"] == "Новое Имя"
    assert updated["email"] == "new@test.local"


async def test_update_profile_creates_client_profile_row(
    db_session: AsyncSession, client_user: User
) -> None:
    updated = await handle_update_client_profile(
        UpdateClientProfileCommand(
            user_id=client_user.id,
            data={
                "client_type": "individual",
                "inn": "771234567890",
                "passport_series": "4500 123456",
            },
        ),
        db_session,
    )
    assert updated["client_type"] == "individual"
    assert updated["inn"] == "771234567890"
    assert updated["profile_id"] is not None


async def test_update_profile_treats_empty_string_as_none(
    db_session: AsyncSession, client_user: User
) -> None:
    await handle_update_client_profile(
        UpdateClientProfileCommand(
            user_id=client_user.id,
            data={"client_type": "individual", "inn": "1234567890"},
        ),
        db_session,
    )
    updated = await handle_update_client_profile(
        UpdateClientProfileCommand(
            user_id=client_user.id, data={"inn": ""}
        ),
        db_session,
    )
    assert updated["inn"] is None
    assert updated["client_type"] == "individual"  # untouched


async def test_update_profile_expires_mobile_id_verification_when_name_changes(
    db_session: AsyncSession, client_user: User
) -> None:
    await handle_update_client_profile(
        UpdateClientProfileCommand(
            user_id=client_user.id,
            data={
                "name": "Даурова Алена Леонтьевна",
                "birth_date": date(1991, 1, 8),
            },
        ),
        db_session,
    )
    verified = await _mark_mobile_id_verified(db_session, client_user)

    updated = await handle_update_client_profile(
        UpdateClientProfileCommand(
            user_id=client_user.id,
            data={"name": "Даурова Алена"},
        ),
        db_session,
    )

    assert updated["name"] == "Даурова Алена"
    latest = await verifications.get_latest_for_user(
        db_session, user_id=client_user.id, provider=verifications.PROVIDER_MOBILE_ID
    )
    assert latest is not None
    assert latest["id"] == verified["id"]
    assert latest["status"] == verifications.STATUS_EXPIRED
    assert latest["verified_at"] is None
    assert latest["failure_code"] == "profile_identity_changed"
    assert (
        await verifications.get_latest_verified_for_user(
            db_session,
            user_id=client_user.id,
            provider=verifications.PROVIDER_MOBILE_ID,
        )
        is None
    )


async def test_update_profile_expires_mobile_id_verification_when_birthdate_changes(
    db_session: AsyncSession, client_user: User
) -> None:
    await handle_update_client_profile(
        UpdateClientProfileCommand(
            user_id=client_user.id,
            data={
                "name": "Даурова Алена Леонтьевна",
                "birth_date": date(1991, 1, 8),
            },
        ),
        db_session,
    )
    verified = await _mark_mobile_id_verified(db_session, client_user)

    updated = await handle_update_client_profile(
        UpdateClientProfileCommand(
            user_id=client_user.id,
            data={"birth_date": date(1992, 1, 8)},
        ),
        db_session,
    )

    assert updated["birth_date"] == date(1992, 1, 8)
    latest = await verifications.get_latest_for_user(
        db_session, user_id=client_user.id, provider=verifications.PROVIDER_MOBILE_ID
    )
    assert latest is not None
    assert latest["id"] == verified["id"]
    assert latest["status"] == verifications.STATUS_EXPIRED
    assert latest["verified_at"] is None


async def test_update_profile_keeps_mobile_id_verification_when_identity_same(
    db_session: AsyncSession, client_user: User
) -> None:
    await handle_update_client_profile(
        UpdateClientProfileCommand(
            user_id=client_user.id,
            data={
                "name": "Даурова Алена Леонтьевна",
                "birth_date": date(1991, 1, 8),
            },
        ),
        db_session,
    )
    verified = await _mark_mobile_id_verified(db_session, client_user)

    updated = await handle_update_client_profile(
        UpdateClientProfileCommand(
            user_id=client_user.id,
            data={
                "name": "  даурова   алена   леонтьевна  ",
                "birth_date": date(1991, 1, 8),
                "email": "same-identity@test.local",
            },
        ),
        db_session,
    )

    assert updated["email"] == "same-identity@test.local"
    latest_verified = await verifications.get_latest_verified_for_user(
        db_session, user_id=client_user.id, provider=verifications.PROVIDER_MOBILE_ID
    )
    assert latest_verified is not None
    assert latest_verified["id"] == verified["id"]
    assert latest_verified["status"] == verifications.STATUS_VERIFIED


# ---------------------------------------------------------------------------
# Phone change
# ---------------------------------------------------------------------------


async def test_request_phone_change_writes_verification_code(
    db_session: AsyncSession, client_user: User
) -> None:
    new_phone = "+76660004567"  # test phone - no SMS sent
    await handle_request_phone_change(
        RequestPhoneChangeCommand(user_id=client_user.id, new_phone=new_phone),
        db_session,
    )
    import sqlalchemy as sa

    rows = (
        await db_session.execute(
            sa.select(VerificationCode).where(VerificationCode.phone == new_phone)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].code == "0000"  # test phone


async def test_request_phone_change_409_if_phone_in_use(
    db_session: AsyncSession,
    client_user: User,
    other_user: User,
) -> None:
    with pytest.raises(PhoneAlreadyInUseError):
        await handle_request_phone_change(
            RequestPhoneChangeCommand(
                user_id=client_user.id, new_phone=other_user.phone
            ),
            db_session,
        )


async def test_verify_phone_change_happy_path(
    db_session: AsyncSession, client_user: User
) -> None:
    new_phone = "+76660004568"
    await handle_request_phone_change(
        RequestPhoneChangeCommand(user_id=client_user.id, new_phone=new_phone),
        db_session,
    )
    await handle_verify_phone_change(
        VerifyPhoneChangeCommand(
            user_id=client_user.id, new_phone=new_phone, code="0000"
        ),
        db_session,
    )
    await db_session.refresh(client_user)
    assert client_user.phone == new_phone
    assert client_user.phone_verified is True


async def test_verify_phone_change_invalid_code(
    db_session: AsyncSession, client_user: User
) -> None:
    new_phone = "+76660004569"
    await handle_request_phone_change(
        RequestPhoneChangeCommand(user_id=client_user.id, new_phone=new_phone),
        db_session,
    )
    with pytest.raises(InvalidPhoneChangeError):
        await handle_verify_phone_change(
            VerifyPhoneChangeCommand(
                user_id=client_user.id, new_phone=new_phone, code="9999"
            ),
            db_session,
        )


async def test_verify_phone_change_expired_code(
    db_session: AsyncSession, client_user: User
) -> None:
    new_phone = "+76660004570"
    db_session.add(
        VerificationCode(
            phone=new_phone,
            code="0000",
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    await db_session.flush()
    with pytest.raises(InvalidPhoneChangeError):
        await handle_verify_phone_change(
            VerifyPhoneChangeCommand(
                user_id=client_user.id, new_phone=new_phone, code="0000"
            ),
            db_session,
        )


# ---------------------------------------------------------------------------
# Saved calculations
# ---------------------------------------------------------------------------


async def test_save_and_list_calculations(
    db_session: AsyncSession, client_user: User
) -> None:
    result = await handle_save_calculation(
        SaveCalculationCommand(
            user_id=client_user.id,
            name="Test calc",
            params={"vehicle_price": 1_000_000},
            calculation={"monthly_payment": 35_000},
        ),
        db_session,
    )
    assert isinstance(result.saved["id"], UUID)
    assert result.saved["name"] == "Test calc"

    items = await handle_list_saved_calculations(
        ListSavedCalculationsQuery(user_id=client_user.id), db_session
    )
    assert len(items) == 1


async def test_delete_calculation_owner_check(
    db_session: AsyncSession, client_user: User, other_user: User
) -> None:
    saved = await handle_save_calculation(
        SaveCalculationCommand(
            user_id=client_user.id,
            name="x",
            params={},
            calculation={},
        ),
        db_session,
    )
    with pytest.raises(AccessDeniedError):
        await handle_delete_saved_calculation(
            DeleteSavedCalculationCommand(
                user_id=other_user.id,
                calculation_id=saved.saved["id"],
            ),
            db_session,
        )


async def test_delete_unknown_calculation_404(
    db_session: AsyncSession, client_user: User
) -> None:
    with pytest.raises(SavedCalculationNotFoundError):
        await handle_delete_saved_calculation(
            DeleteSavedCalculationCommand(
                user_id=client_user.id, calculation_id=uuid4()
            ),
            db_session,
        )


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------


async def test_add_favorite_then_list(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    added = await handle_add_favorite(
        AddFavoriteCommand(user_id=client_user.id, vehicle_id=vehicle.id),
        db_session,
    )
    assert added["vehicle_id"] == vehicle.id

    favorites = await handle_list_favorites(
        ListFavoritesQuery(user_id=client_user.id), db_session
    )
    assert any(f["vehicle_id"] == vehicle.id for f in favorites)


async def test_add_duplicate_favorite_raises_conflict(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    await handle_add_favorite(
        AddFavoriteCommand(user_id=client_user.id, vehicle_id=vehicle.id),
        db_session,
    )
    with pytest.raises(FavoriteAlreadyExistsError):
        await handle_add_favorite(
            AddFavoriteCommand(user_id=client_user.id, vehicle_id=vehicle.id),
            db_session,
        )


async def test_remove_favorite_idempotent(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    removed = await handle_remove_favorite(
        RemoveFavoriteCommand(user_id=client_user.id, vehicle_id=vehicle.id),
        db_session,
    )
    assert removed is False

    db_session.add(UserFavorite(user_id=client_user.id, vehicle_id=vehicle.id))
    await db_session.flush()
    removed_now = await handle_remove_favorite(
        RemoveFavoriteCommand(user_id=client_user.id, vehicle_id=vehicle.id),
        db_session,
    )
    assert removed_now is True


async def test_bulk_remove_favorites_only_users_own(
    db_session: AsyncSession, client_user: User, other_user: User
) -> None:
    v1 = await _seed_vehicle(db_session)
    v2 = await _seed_vehicle(db_session)
    db_session.add(UserFavorite(user_id=client_user.id, vehicle_id=v1.id))
    db_session.add(UserFavorite(user_id=client_user.id, vehicle_id=v2.id))
    db_session.add(UserFavorite(user_id=other_user.id, vehicle_id=v1.id))
    await db_session.flush()

    removed = await handle_bulk_remove_favorites(
        BulkRemoveFavoritesCommand(
            user_id=client_user.id, vehicle_ids=(v1.id, v2.id)
        ),
        db_session,
    )
    assert removed == 2

    # other_user's favorite is untouched
    others = await handle_list_favorites(
        ListFavoritesQuery(user_id=other_user.id), db_session
    )
    assert len(others) == 1
    assert others[0]["vehicle_id"] == v1.id


async def test_list_favorites_orders_newest_first(
    db_session: AsyncSession, client_user: User
) -> None:
    v1 = await _seed_vehicle(db_session)
    v2 = await _seed_vehicle(db_session)
    older = UserFavorite(
        user_id=client_user.id,
        vehicle_id=v1.id,
        added_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newer = UserFavorite(
        user_id=client_user.id,
        vehicle_id=v2.id,
        added_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    db_session.add_all([older, newer])
    await db_session.flush()

    items = await handle_list_favorites(
        ListFavoritesQuery(user_id=client_user.id), db_session
    )
    assert [it["vehicle_id"] for it in items] == [v2.id, v1.id]

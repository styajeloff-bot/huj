"""Unit / handler tests for the dealer cabinet (Phase 5 E3)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.dealer import (
    InviteClientCommand,
    handle_invite_client,
)
from domain.errors import DealerInviteError
from infrastructure.models.companies import Company
from infrastructure.models.users import User, VerificationCode

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def dealer_user(db_session: AsyncSession) -> User:
    user = User(
        phone="+76660000001",
        email="dealerhandler@test.local",
        name="Dealer Handler",
        role="dealer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def dealer_company(db_session: AsyncSession) -> Company:
    c = Company(name="Dealer Test Co", company_type="other")
    db_session.add(c)
    await db_session.flush()
    return c


# ---------------------------------------------------------------------------
# invite-client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invite_client_creates_new_user(
    db_session: AsyncSession,
    dealer_user: User,
) -> None:
    phone = "+76660004567"
    cmd = InviteClientCommand(
        actor_id=dealer_user.id,
        actor_role="dealer",
        phone=phone,
        name="Приглашённый",
    )

    with patch(
        "application.commands.dealer.invite_client.sms_service.send_verification_sms",
        new=AsyncMock(),
    ):
        result = await handle_invite_client(cmd, db_session)

    assert result["success"] is True
    assert result["created_user"] is True

    created = await db_session.execute(sa.select(User).where(User.phone == phone))
    created_user = created.scalars().first()
    assert created_user is not None
    assert created_user.role == "client"
    assert created_user.name == "Приглашённый"

    code_row = await db_session.execute(
        sa.select(VerificationCode).where(VerificationCode.phone == phone)
    )
    assert code_row.scalars().first() is not None


@pytest.mark.asyncio
async def test_invite_client_existing_user_is_silent_noop(
    db_session: AsyncSession,
    dealer_user: User,
) -> None:
    phone = "+76660001111"
    existing = User(
        phone=phone,
        email=None,
        name="Existing",
        role="client",
        is_active=True,
    )
    db_session.add(existing)
    await db_session.flush()

    cmd = InviteClientCommand(
        actor_id=dealer_user.id, actor_role="dealer", phone=phone
    )
    with patch(
        "application.commands.dealer.invite_client.sms_service.send_verification_sms",
        new=AsyncMock(),
    ):
        result = await handle_invite_client(cmd, db_session)

    assert result["success"] is True
    # Existing account — no new user row created.
    assert result["created_user"] is False


@pytest.mark.asyncio
async def test_invite_client_rejects_invalid_phone(
    db_session: AsyncSession,
    dealer_user: User,
) -> None:
    cmd = InviteClientCommand(
        actor_id=dealer_user.id,
        actor_role="dealer",
        phone="not-a-phone",
    )
    with pytest.raises(DealerInviteError):
        await handle_invite_client(cmd, db_session)


@pytest.mark.asyncio
async def test_invite_client_rejects_non_dealer_role(
    db_session: AsyncSession, dealer_user: User
) -> None:
    cmd = InviteClientCommand(
        actor_id=dealer_user.id,
        actor_role="client",
        phone="+76660004567",
    )
    with pytest.raises(DealerInviteError):
        await handle_invite_client(cmd, db_session)


@pytest.mark.asyncio
async def test_invite_client_normalises_phone_formats(
    db_session: AsyncSession, dealer_user: User
) -> None:
    cmd = InviteClientCommand(
        actor_id=dealer_user.id,
        actor_role="dealer",
        phone="89991234567",  # 8 prefix
    )
    with patch(
        "application.commands.dealer.invite_client.sms_service.send_verification_sms",
        new=AsyncMock(),
    ):
        result = await handle_invite_client(cmd, db_session)
    assert result["success"] is True

    created = (
        await db_session.execute(
            sa.select(User).where(User.phone == "+79991234567")
        )
    ).scalars().first()
    assert created is not None


# ---------------------------------------------------------------------------
# list_dealer_vehicles




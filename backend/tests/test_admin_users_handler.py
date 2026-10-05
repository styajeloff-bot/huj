"""Unit tests for admin_users command/query handlers."""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.admin_users import (
    CreateUserCommand,
    DeleteUserCommand,
    UpdateUserCommand,
    handle_create_user,
    handle_delete_user,
    handle_update_user,
)
from application.queries.admin_users import (
    ListUsersQuery,
    handle_list_users,
)
from domain.errors import (
    InvalidRoleError,
    UserAlreadyExistsError,
    UserEmailAlreadyExistsError,
    UserNotFoundError,
)
from infrastructure.models.users import User

pytestmark = pytest.mark.asyncio


async def test_create_user_happy_path(db_session: AsyncSession) -> None:
    cmd = CreateUserCommand(
        name="Alice",
        email="alice@test.local",
        phone="+76660001001",
        role="dealer",
        company_id=None,
        is_active=True,
        email_verified=True,
    )
    user = await handle_create_user(cmd, db_session)
    assert user["name"] == "Alice"
    assert user["role"] == "dealer"
    assert user["is_active"] is True


async def test_create_user_invalid_role_raises(
    db_session: AsyncSession,
) -> None:
    cmd = CreateUserCommand(
        name="Bob",
        email="bob@test.local",
        phone="+76660001002",
        role="not-a-real-role",
    )
    with pytest.raises(InvalidRoleError):
        await handle_create_user(cmd, db_session)


async def test_create_user_duplicate_email_raises(
    db_session: AsyncSession,
) -> None:
    existing = User(
        phone="+76660001003",
        email="dup@test.local",
        name="Existing",
        role="client",
        is_active=True,
    )
    db_session.add(existing)
    await db_session.flush()

    cmd = CreateUserCommand(
        name="New",
        email="dup@test.local",
        phone="+76660001004",
        role="client",
    )
    with pytest.raises(UserEmailAlreadyExistsError):
        await handle_create_user(cmd, db_session)


async def test_create_user_duplicate_phone_raises(
    db_session: AsyncSession,
) -> None:
    existing = User(
        phone="+76660001005",
        email="phone-dup@test.local",
        name="Existing Phone",
        role="client",
        is_active=True,
    )
    db_session.add(existing)
    await db_session.flush()

    cmd = CreateUserCommand(
        name="New",
        email="phone-dup2@test.local",
        phone="+76660001005",
        role="client",
    )
    with pytest.raises(UserAlreadyExistsError):
        await handle_create_user(cmd, db_session)


async def test_update_user_happy_path(db_session: AsyncSession) -> None:
    user = User(
        phone="+76660002001",
        email="upd@test.local",
        name="To Update",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    cmd = UpdateUserCommand(
        user_id=user.id,
        fields={"name": "Updated Name", "is_active": False},
    )
    result = await handle_update_user(cmd, db_session)
    assert result["name"] == "Updated Name"
    assert result["is_active"] is False


async def test_update_user_missing_raises(db_session: AsyncSession) -> None:
    with pytest.raises(UserNotFoundError):
        await handle_update_user(
            UpdateUserCommand(user_id=uuid4(), fields={"name": "x"}),
            db_session,
        )


async def test_update_user_invalid_role_raises(
    db_session: AsyncSession,
) -> None:
    user = User(
        phone="+76660002002",
        email="badrole@test.local",
        name="u",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(InvalidRoleError):
        await handle_update_user(
            UpdateUserCommand(
                user_id=user.id, fields={"role": "bogus-role"}
            ),
            db_session,
        )


async def test_delete_user_is_soft_delete(
    db_session: AsyncSession,
) -> None:
    user = User(
        phone="+76660003001",
        email="del@test.local",
        name="Del",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    result = await handle_delete_user(
        DeleteUserCommand(user_id=user.id), db_session
    )
    assert result["id"] == user.id
    # Soft-delete: record still exists, just is_active=False
    await db_session.refresh(user)
    assert user.is_active is False


async def test_delete_user_missing_raises(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(UserNotFoundError):
        await handle_delete_user(
            DeleteUserCommand(user_id=uuid4()), db_session
        )


async def test_list_users_filters_by_role(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            User(
                phone="+76660004001",
                email="a@test.local",
                name="D1",
                role="dealer",
                is_active=True,
            ),
            User(
                phone="+76660004002",
                email="b@test.local",
                name="C1",
                role="client",
                is_active=True,
            ),
        ]
    )
    await db_session.flush()

    result = await handle_list_users(
        ListUsersQuery(role="dealer"), db_session
    )
    assert result["pagination"]["total"] >= 1
    assert all(u["role"] == "dealer" for u in result["users"])

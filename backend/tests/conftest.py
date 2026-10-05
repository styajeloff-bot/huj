
"""
Integration test fixtures using an external PostgreSQL database.

Schema is created via SQLAlchemy metadata (same models used by Alembic),
then every test gets a fresh DB session whose transaction is rolled back.
"""
import os

from tests.legacy_compat import Vehicle, VehicleCategory

# Minimal env vars so pydantic-settings doesn't blow up on import.
# The real DATABASE_URL is set below after the container starts.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "password")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault(
    "JWT_ACCESS_SECRET",
    "faw-leasing-access-secret-key-2024-very-long-and-secure",
)
os.environ.setdefault("EXPRESS_URL", "http://localhost:3001")
# Tests run without a real Redis — fakeredis is injected via fixture below.
# These defaults just keep pydantic-settings happy during module import.
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

import asyncio
from collections.abc import AsyncGenerator, Generator
from decimal import Decimal
from typing import Any, cast

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from infrastructure.auth import generate_tokens
from infrastructure.cache import set_redis
from infrastructure.database import get_db
from infrastructure.models import Base
from infrastructure.models.users import User
from infrastructure.services.company_enrichment import set_company_enrichment_scheduler

# ---------------------------------------------------------------------------
# Session-scoped: install an in-memory ES256 keypair before any test runs.
# No disk I/O, no env var manipulation — the setter replaces the module-level
# key registry directly.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _jwt_dev_keys() -> Generator[None, None, None]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from infrastructure.crypto.jwt_keys import set_dev_keys

    priv = ec.generate_private_key(ec.SECP256R1())
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    set_dev_keys(priv_pem, pub_pem, kid="test-es256")
    yield


# ---------------------------------------------------------------------------
# Session-scoped: connect to external PostgreSQL and create schema
# ---------------------------------------------------------------------------

_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:password@localhost:5433/carcraft_test",
)


def _ensure_database_exists(async_url: str) -> None:
    """Create the configured test database after a fresh Postgres volume reset."""

    url = make_url(async_url)
    database = url.database
    if not database:
        return

    admin_url = url.set(database="postgres")

    async def _inner() -> None:
        engine = create_async_engine(
            admin_url,
            isolation_level="AUTOCOMMIT",
            poolclass=NullPool,
        )
        async with engine.connect() as conn:
            exists = await conn.scalar(
                sa.text("SELECT 1 FROM pg_database WHERE datname = :database"),
                {"database": database},
            )
            if exists is None:
                quoted_database = '"' + database.replace('"', '""') + '"'
                await conn.execute(sa.text(f"CREATE DATABASE {quoted_database}"))
        await engine.dispose()

    asyncio.run(_inner())


def _create_schema(async_url: str) -> None:
    """Create all tables using SQLAlchemy metadata.create_all."""

    async def _inner() -> None:
        engine = create_async_engine(async_url, poolclass=NullPool)
        async with engine.begin() as conn:
            # Revisions 082 and 142 removed legacy tables from the ORM metadata.
            # A reused test database may still contain their FKs to products,
            # which otherwise prevents ``drop_all`` from resetting the schema.
            await conn.execute(
                sa.text(
                    "DROP TABLE IF EXISTS "
                    "special_equipment_product_attribute_values CASCADE"
                )
            )
            await conn.execute(
                sa.text(
                    "DROP TABLE IF EXISTS "
                    "special_equipment_product_components CASCADE"
                )
            )
            await conn.execute(
                sa.text(
                    "DROP TABLE IF EXISTS "
                    "special_equipment_superstructures CASCADE"
                )
            )
            await conn.run_sync(Base.metadata.drop_all)
            # Task 21940 indexes case-insensitive contains filters with pg_trgm.
            # Alembic owns the extension in deployed databases; metadata-driven
            # tests need the same prerequisite before ``create_all``.
            await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await conn.run_sync(Base.metadata.create_all)
            # Revision 051 owns these rows in deployed databases. Metadata
            # fixtures need the same catalog for the real car_status FK.
            await conn.execute(
                sa.text(
                    "INSERT INTO cars_status (status_name, status_display_name) "
                    "VALUES (:name, :display_name)"
                ),
                [
                    {"name": "confirmed", "display_name": "Подтверждено"},
                    {"name": "not_confirmed", "display_name": "Не подтверждено"},
                    {"name": "active", "display_name": "Подтверждается"},
                    {"name": "replacement", "display_name": "Замена ТС"},
                ],
            )
            await conn.execute(
                sa.text(
                    "INSERT INTO catalog_storefronts "
                    "(id, slug, is_default, is_active, version, "
                    "contact_email, contact_phone) VALUES "
                    "('00000000-0000-0000-0000-000000000001', NULL, "
                    "TRUE, TRUE, 1, 'info@multileasing.ru', "
                    "'+7 (930) 999-03-65')"
                )
            )
            await conn.execute(
                sa.text(
                    "INSERT INTO special_equipment_catalog_state "
                    "(singleton, revision) VALUES (TRUE, 0)"
                )
            )
        await engine.dispose()

    asyncio.run(_inner())


@pytest.fixture(scope="session")
def _engine() -> Generator[AsyncEngine, None, None]:
    """Create a single async engine for the test session."""
    _ensure_database_exists(_TEST_DB_URL)
    _create_schema(_TEST_DB_URL)
    engine = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
    try:
        yield engine
    finally:
        asyncio.run(engine.dispose())


# ---------------------------------------------------------------------------
# Per-test: rolled-back transaction
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session(_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Wraps the test in a DB transaction that is always rolled back."""
    conn = await _engine.connect()
    trans = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False)

    # Patch session.commit → flush so the router's `await session.commit()`
    # makes data visible inside the test without actually committing to the DB.
    async def _flush_only() -> None:
        await session.flush()

    session.commit = _flush_only  # type: ignore[method-assign]

    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()


@pytest_asyncio.fixture
async def default_vehicle_category_id(db_session: AsyncSession) -> str:

    category_id = "B (Легковые автомобили)"
    if await db_session.get(VehicleCategory, category_id) is None:
        db_session.add(VehicleCategory(id=category_id, parent_id=None))
        await db_session.flush()
    return category_id


# ---------------------------------------------------------------------------
# HTTP client — wired to the rolled-back session
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _fake_redis() -> Generator[None, None, None]:
    """Route all Redis traffic through an in-memory fake for the test run.

    The denylist code path calls `infrastructure.cache.get_redis()` on every
    authenticated request, so we must install a fake before any request runs.
    """
    import fakeredis.aioredis

    from infrastructure.cache.redis_client import RedisLike

    fake = cast("RedisLike", fakeredis.aioredis.FakeRedis())
    set_redis(fake)
    try:
        yield
    finally:
        set_redis(None)


class _CookieInjectingClient(AsyncClient):
    """Test client that converts ``Authorization: Bearer <token>`` into an
    ``accessToken`` cookie. This lets tests keep writing
    ``headers=_auth(token)`` while the server receives cookie-based auth
    (the same way real browsers work).

    Also absorbs per-request ``cookies=`` into the client instance to avoid
    httpx's deprecation warning about per-request cookie persistence.
    """

    async def request(  # type: ignore[override]
        self, method: str, url: str, **kwargs: Any
    ) -> Any:
        headers = dict(kwargs.pop("headers", {}) or {})
        auth = headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            self.cookies.set("accessToken", auth[7:])
            headers.pop("Authorization", None)
        if headers:
            kwargs["headers"] = headers

        # Serialize UUID in json body for tests
        if kwargs.get("json") is not None:
            import json
            from uuid import UUID
            class UUIDEncoder(json.JSONEncoder):
                def default(self, obj: Any) -> str:
                    if isinstance(obj, UUID):
                        return str(obj)
                    return str(super().default(obj))
            kwargs["content"] = json.dumps(kwargs.pop("json"), cls=UUIDEncoder)
            headers["content-type"] = "application/json"
            kwargs["headers"] = headers
        elif headers:
            kwargs["headers"] = headers

        # Merge per-request cookies into the client instance (avoids deprecation).
        req_cookies = kwargs.pop("cookies", None)
        if req_cookies:
            for name, value in req_cookies.items():
                self.cookies.set(name, value)

        # Remove empty headers to let httpx set defaults (e.g. multipart boundary)
        if "headers" in kwargs and not kwargs.get("headers"):
            del kwargs["headers"]

        return await super().request(method, url, **kwargs)


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from main import app

    class _NoopScheduler:
        async def schedule_refresh(self, inn: str) -> None:
            return None

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    set_company_enrichment_scheduler(_NoopScheduler())
    async with _CookieInjectingClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
    set_company_enrichment_scheduler(None)


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client_user(db_session: AsyncSession) -> User:
    user = User(
        phone="+76660000001",
        email="testclient@test.local",
        name="Test Client",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def employee_user(db_session: AsyncSession) -> User:
    user = User(
        phone="+76660000002",
        email="testemployee@test.local",
        name="Test Employee",
        role="carcraft_employee",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    """A second client — used for ownership-check tests."""
    user = User(
        phone="+76660000003",
        email="testother@test.local",
        name="Other Client",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Vehicle fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def test_vehicle(db_session: AsyncSession) -> Vehicle:
    """A minimal available vehicle with a base price."""
    vehicle = Vehicle(
        status="available",
        is_available=True,
        base_price=Decimal("2000000.00"),
    )
    db_session.add(vehicle)
    await db_session.flush()
    await db_session.refresh(vehicle)
    return vehicle


# ---------------------------------------------------------------------------
# JWT token helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def client_token(client_user: User) -> str:
    token, _ = generate_tokens(client_user.id, "client", None)
    return token


@pytest.fixture
def employee_token(employee_user: User) -> str:
    token, _ = generate_tokens(employee_user.id, "carcraft_employee", None)
    return token


@pytest.fixture
def other_token(other_user: User) -> str:
    token, _ = generate_tokens(other_user.id, "client", None)
    return token


# ---------------------------------------------------------------------------
# Auth test fixtures — users with test phone numbers (code is always '0000')
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def test_phone_user(db_session: AsyncSession) -> User:
    """User with a test phone — SMS is never sent, code is always '0000'."""
    user = User(
        phone="+76660004567",
        email="testphone@test.local",
        name="Test Phone User",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def test_phone_token(test_phone_user: User) -> str:
    token, _ = generate_tokens(test_phone_user.id, "client", None)
    return token

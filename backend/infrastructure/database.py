"""Database infrastructure: async engine, session factory, dependency."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from infrastructure.settings import settings

engine = create_async_engine(
    settings.database_dsn,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
)

# NOTE: expire_on_commit=False is an intentional project invariant.
#
# Rationale:
#   * Repositories in `infrastructure/repositories/` return plain
#     `dict` / `list[dict]` — never ORM objects. Callers (application layer,
#     domain entities hydrated via `.from_dict`) therefore never touch lazy
#     attributes after a commit, so the default SQLAlchemy behaviour of
#     expiring all instances on commit would only cause needless re-loads
#     and surprise `MissingGreenlet` errors in async code paths.
#   * Routers commit the session (`await session.commit()`) after handlers
#     return; with expire_on_commit=True any dict that was built from an
#     ORM row *before* commit could still be safe, but any code that kept
#     a reference to an ORM instance would silently break.
#
# Invariant: if a repository ever starts returning ORM objects, the caller
# MUST either `await session.refresh(obj)` after commit, or this flag must
# be flipped to True. Do not return ORM objects without addressing this.
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


def get_pool_status() -> dict[str, int | str]:
    """Return a logging-safe snapshot of the current SQLAlchemy pool state."""
    pool = engine.pool

    def _call_int(name: str) -> int | str:
        value = getattr(pool, name, None)
        if value is None:
            return "unavailable"
        try:
            result = value() if callable(value) else value
        except Exception:
            return "unavailable"
        return result if isinstance(result, int) else "unavailable"

    status = getattr(pool, "status", None)
    try:
        status_text = status() if callable(status) else str(status)
    except Exception:
        status_text = "unavailable"

    return {
        "size": _call_int("size"),
        "checked_out": _call_int("checkedout"),
        "overflow": _call_int("overflow"),
        "status": status_text,
    }


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for async DB session."""
    async with AsyncSessionLocal() as session:
        yield session

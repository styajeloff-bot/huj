"""Company-scoped permission helpers.

Fine-grained permissions (sub_role, can_view_applications, can_create_applications)
live on the ``user_companies`` join table. These helpers load them on demand so
that permission changes take effect immediately without token re-issuance.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import (
    resolve_distributor_application_dealer_filter,
)
from application.services.leasing_access import require_lc_application_access
from domain.entities.leasing_application import LeasingApplication
from domain.errors import ApplicationNotOwnedError, CompanyAccessDeniedError
from infrastructure.repositories import application_repository as application_repo
from infrastructure.repositories import company_registration_repository as company_repo


async def get_company_permissions(
    session: AsyncSession, user_id: UUID, company_id: UUID | None
) -> dict[str, Any]:
    """Return permission dict for a user in a specific company."""
    if company_id is None:
        return {
            "sub_role": None,
            "can_view_applications": False,
            "can_create_applications": False,
        }
    perms: dict[str, Any] = await company_repo.get_company_permissions(
        session, user_id, company_id
    )
    return perms


def is_company_admin_or_manager(permissions: dict[str, Any]) -> bool:
    return permissions.get("sub_role") in {"administrator", "manager"}


async def require_distributor_application_read(
    session: AsyncSession, *, user_id: UUID, actor_role: str,
    actor_company_id: UUID | None,
) -> None:
    """Distributor object scope never substitutes for current read permission.

    This guard belongs to reads, not company selection or creation: a user may
    retain independent creation rights after application read access is revoked.
    Other roles keep their existing read rules, including client author access.
    """
    if actor_role != "distributor":
        return
    permissions = await get_company_permissions(session, user_id, actor_company_id)
    if not permissions.get("can_view_applications"):
        raise CompanyAccessDeniedError("Просмотр заявок ограничен администратором компании")


async def ensure_application_visible_to(
    session: AsyncSession,
    *,
    application: dict[str, Any],
    user_id: UUID,
    actor_role: str,
    actor_company_id: UUID | None,
    actor_leasing_company_id: UUID | None = None,
) -> LeasingApplication:
    """Allow parent owners and dealers that own any mixed child to read."""

    await require_distributor_application_read(
        session, user_id=user_id, actor_role=actor_role,
        actor_company_id=actor_company_id,
    )
    if actor_role in ("dealer", "distributor") and actor_company_id is not None:
        from infrastructure.repositories.application_personal_access import (
            check_application_personal_access,
        )
        from infrastructure.repositories.user_company_access_repository import (
            check_section_access,
        )

        if not await check_section_access(
            session,
            user_id=user_id,
            company_id=actor_company_id,
            role=actor_role,
            section_code="applications",
        ):
            raise CompanyAccessDeniedError("У вас нет доступа к этому разделу")

        app_id_raw = application.get("id")
        if app_id_raw is not None:
            can_access = await check_application_personal_access(
                session,
                application_id=UUID(str(app_id_raw)),
                user_id=user_id,
                company_id=actor_company_id,
                role=actor_role,
            )
            if not can_access:
                raise ApplicationNotOwnedError()

    entity = LeasingApplication.from_dict(application)
    if actor_role == "leasing_company":
        await require_lc_application_access(
            session, application_id=entity.id, user_id=user_id,
            company_id=actor_company_id, leasing_company_id=actor_leasing_company_id,
        )
        return entity
    if actor_role == "distributor":
        dealer_filter = await resolve_distributor_application_dealer_filter(
            session,
            actor_id=user_id,
            actor_role=actor_role,
            company_id=actor_company_id,
        )
        if await application_repo.distributor_can_view_application(
            session,
            application_id=entity.id,
            dealer_ids=dealer_filter,
            distributor_company_id=actor_company_id,
        ):
            return entity
        raise ApplicationNotOwnedError()
    if (
        actor_role == "dealer"
        and actor_company_id is not None
        and await application_repo.dealer_company_owns_application_item(
            session,
            application_id=entity.id,
            company_id=actor_company_id,
        )
    ):
        return entity
    entity.ensure_owned_by(
        user_id=user_id,
        role=actor_role,
        company_id=actor_company_id,
        leasing_company_id=actor_leasing_company_id,
    )
    return entity


async def ensure_application_owned_by(
    session: AsyncSession,
    *,
    application: dict[str, Any],
    user_id: UUID,
    actor_role: str,
    actor_company_id: UUID | None,
    actor_leasing_company_id: UUID | None = None,
) -> LeasingApplication:
    """Apply parent ownership for mutations; child ownership is read-only."""

    del session
    entity = LeasingApplication.from_dict(application)
    entity.ensure_owned_by(
        user_id=user_id,
        role=actor_role,
        company_id=actor_company_id,
        leasing_company_id=actor_leasing_company_id,
    )
    return entity


async def ensure_application_full_data_access(
    session: AsyncSession, *, application_id: UUID, actor_role: str,
    actor_company_id: UUID | None,
) -> None:
    """After ordinary authorization, protect indivisible financials/exports.

    Whole-application proposals and documents cannot be apportioned safely to
    the new partial recipient. Existing owners and full assignees are unchanged.
    """
    if (
        actor_role == "dealer"
        and actor_company_id is not None
        and await application_repo.dealer_distribution_requires_scoped_read(
            session, application_id=application_id, company_id=actor_company_id,
        )
    ):
        raise ApplicationNotOwnedError(
            "Полные финансовые данные и экспорт недоступны при частичном распределении автомобилей"
        )


async def ensure_application_vehicle_action_allowed(
    session: AsyncSession,
    *,
    application: dict[str, Any],
    application_vehicle_id: UUID,
    user_id: UUID,
    actor_role: str,
    actor_company_id: UUID | None,
    actor_leasing_company_id: UUID | None = None,
) -> LeasingApplication:
    """Authorize a vehicle action against its exact child row.

    A secondary vehicle seller may act on its own ``application_vehicles``
    row, but ownership of an unrelated vehicle or special-equipment line must
    not grant access to this target.
    """

    from application.dealer_distribution_access import (
        ensure_whole_vehicle_write_allowed,
    )

    entity = LeasingApplication.from_dict(application)
    if actor_role == "dealer":
        if (
            actor_company_id is not None
            and await application_repo.dealer_company_owns_application_vehicle(
                session,
                application_vehicle_id=application_vehicle_id,
                company_id=actor_company_id,
            )
        ):
            await ensure_whole_vehicle_write_allowed(
                session, application_vehicle_id=application_vehicle_id,
                actor_role=actor_role, actor_company_id=actor_company_id,
            )
            return entity
        raise ApplicationNotOwnedError()
    if actor_role == "distributor":
        dealer_filter = await resolve_distributor_application_dealer_filter(
            session,
            actor_id=user_id,
            actor_role=actor_role,
            company_id=actor_company_id,
        )
        if await application_repo.distributor_can_view_application_vehicle(
            session,
            application_vehicle_id=application_vehicle_id,
            dealer_ids=dealer_filter,
            distributor_company_id=actor_company_id,
        ):
            await ensure_whole_vehicle_write_allowed(
                session, application_vehicle_id=application_vehicle_id,
                actor_role=actor_role, actor_company_id=actor_company_id,
            )
            return entity
        raise ApplicationNotOwnedError()

    entity.ensure_owned_by(
        user_id=user_id,
        role=actor_role,
        company_id=actor_company_id,
        leasing_company_id=actor_leasing_company_id,
    )
    return entity


async def require_can_create_applications(
    session: AsyncSession,
    user_id: UUID,
    company_id: UUID,
    actor_role: str,
) -> None:
    """Raise ServiceError(403) if the user lacks create permission for the company."""
    if actor_role in {
        "carcraft_employee",
        "distributor",
        "leasing_company",
        "external_api",
    }:
        return
    perms = await get_company_permissions(session, user_id, company_id)
    if not perms.get("can_create_applications"):
        from application.errors import ServiceError

        raise ServiceError("Создание заявок ограничено администратором компании", 403)


async def require_can_mutate_application(
    session: AsyncSession,
    *,
    user_id: UUID,
    actor_role: str,
    actor_company_id: UUID | None,
    application: dict[str, Any],
) -> None:
    """Allow parent mutation by company permission or primary dealer ownership."""
    if actor_role == "dealer":
        dealer_company_id = application.get("dealer_company_id")
        if actor_company_id is not None and dealer_company_id == actor_company_id:
            return
    await require_can_create_applications(
        session,
        user_id,
        application["company_id"],
        actor_role,
    )


async def check_section_access(
    session: AsyncSession,
    *,
    user_id: UUID,
    company_id: UUID | None,
    role: str,
    section_code: str,
) -> bool:
    """Check user's section access."""
    from infrastructure.repositories.user_company_access_repository import (
        check_section_access as repo_check,
    )

    return await repo_check(
        session,
        user_id=user_id,
        company_id=company_id,
        role=role,
        section_code=section_code,
    )


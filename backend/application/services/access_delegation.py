"""Access delegation enforcement and anti-privilege-escalation service."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.repositories.user_company_access_repository import (
    check_can_create_employees,
    get_user_company_access_rules,
    get_user_company_by_user_and_company,
    get_user_company_section_access,
)


def _check_none_mode(
    obj_type: str,
    t_access_type: str,
    t_ids: set[str],
    target_user_id: UUID,
) -> None:
    if t_access_type != "none":
        if (
            obj_type == "application_creator"
            and t_access_type == "selected"
            and t_ids == {str(target_user_id)}
        ):
            return
        raise ServiceError("Нельзя предоставить сотруднику права, которыми вы не обладаете", 400)


def _check_selected_mode(
    obj_type: str,
    t_access_type: str,
    t_ids: set[str],
    g_ids: set[str],
    target_user_id: UUID,
) -> None:
    if t_access_type in ("all", "except_selected"):
        raise ServiceError("Нельзя предоставить сотруднику права, которыми вы не обладаете", 400)
    if t_access_type == "selected":
        for target_id in t_ids:
            if target_id not in g_ids:
                if obj_type == "application_creator" and target_id == str(target_user_id):
                    continue
                raise ServiceError(
                    "Нельзя предоставить сотруднику права, которыми вы не обладаете", 400
                )


def _check_except_selected_mode(
    obj_type: str,
    t_access_type: str,
    t_ids: set[str],
    g_ids: set[str],
    target_user_id: UUID,
) -> None:
    if t_access_type == "all":
        raise ServiceError("Нельзя предоставить сотруднику права, которыми вы не обладаете", 400)
    if t_access_type == "selected":
        for target_id in t_ids:
            if target_id in g_ids:
                if obj_type == "application_creator" and target_id == str(target_user_id):
                    continue
                raise ServiceError(
                    "Нельзя предоставить сотруднику права, которыми вы не обладаете", 400
                )
    elif t_access_type == "except_selected" and not g_ids.issubset(t_ids):
        raise ServiceError("Нельзя предоставить сотруднику права, которыми вы не обладаете", 400)


def _validate_single_object_type(
    obj_type: str,
    t_rules: list[dict[str, Any]],
    g_rules: list[Any],
    target_user_id: UUID,
) -> None:
    if not t_rules or not g_rules:
        return

    t_access_type = str(t_rules[0].get("access_type", "all"))
    t_ids = {str(r.get("object_id")) for r in t_rules if r.get("object_id") is not None}
    g_access_type = g_rules[0].access_type
    g_ids = {str(r.object_id) for r in g_rules if r.object_id is not None}

    if g_access_type == "none":
        _check_none_mode(obj_type, t_access_type, t_ids, target_user_id)
    elif g_access_type == "selected":
        _check_selected_mode(obj_type, t_access_type, t_ids, g_ids, target_user_id)
    elif g_access_type == "except_selected":
        _check_except_selected_mode(obj_type, t_access_type, t_ids, g_ids, target_user_id)


async def validate_delegation(
    session: AsyncSession,
    *,
    granter_user_id: UUID,
    granter_role: str,
    granter_company_id: UUID | None,
    target_user_id: UUID,
    target_company_id: UUID,
    target_user_company_id: UUID,
    target_rules: list[dict[str, Any]],
    target_sections: dict[str, bool],
    target_can_create_employees: bool,
) -> None:
    """Validate that granter has rights to configure target and is not escalating privileges."""
    if granter_role == "carcraft_employee":
        return
    del target_user_company_id

    if granter_user_id == target_user_id:
        raise ServiceError("Нельзя изменять свои собственные права доступа", 400)

    if granter_company_id is None or granter_company_id != target_company_id:
        raise ServiceError("Нельзя настраивать сотрудников другой компании", 403)

    granter_uc = await get_user_company_by_user_and_company(
        session, granter_user_id, granter_company_id
    )
    if granter_uc is None or not granter_uc.is_active:
        raise ServiceError("Недостаточно прав для управления сотрудниками", 403)

    has_perm = await check_can_create_employees(
        session,
        user_company_id=granter_uc.id,
        sub_role=granter_uc.sub_role,
        role=granter_uc.role,
    )
    if not has_perm or (target_can_create_employees and not has_perm):
        raise ServiceError("Недостаточно прав для управления сотрудниками", 403)

    # Validate section access
    granter_sections = await get_user_company_section_access(session, granter_uc.id)
    for section_code, can_view in target_sections.items():
        if can_view and not granter_sections.get(section_code, True):
            raise ServiceError("Нельзя предоставить сотруднику права, которыми вы не обладаете", 400)

    # Validate object access rules
    granter_rules = await get_user_company_access_rules(session, granter_uc.id)
    g_by_obj: dict[str, list[Any]] = {}
    for r in granter_rules:
        g_by_obj.setdefault(r.access_object, []).append(r)

    t_by_obj: dict[str, list[dict[str, Any]]] = {}
    for rule_dict in target_rules:
        ot = str(rule_dict.get("access_object", ""))
        if ot:
            t_by_obj.setdefault(ot, []).append(rule_dict)

    for ot, t_rules in t_by_obj.items():
        _validate_single_object_type(ot, t_rules, g_by_obj.get(ot, []), target_user_id)

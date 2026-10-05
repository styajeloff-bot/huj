"""Administrative partial update of a company profile."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.companies.update_company import (
    UpdateCompanyCommand,
    build_company_changed_event,
    handle_update_company,
)
from application.errors import ServiceError
from domain.errors import CompanyNotFoundError
from infrastructure.repositories import (
    company_change_history_repository as history_repo,
)
from infrastructure.repositories import (
    company_repository as company_repo,
)
from infrastructure.repositories import (
    company_type_transition_repository as transition_repo,
)

_EDITABLE_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "company_type",
        "inn",
        "kpp",
        "ogrn",
        "is_active",
        "phone",
        "email",
        "website",
        "legal_address",
        "actual_address",
    }
)
_COMPANY_TYPES: frozenset[str] = frozenset(
    {"dealer", "leasing_company", "distributor", "other"}
)
_SPECIALIZED_TYPES: frozenset[str] = frozenset({"leasing_company", "distributor"})

_BLOCKER_PRESENTATION: dict[str, tuple[str, str]] = {
    "missing_leasing_extension": ("Отсутствует профиль лизинговой компании", "Проверьте и восстановите профиль лизинговой компании перед сменой типа."),
    "missing_distributor_extension": ("Отсутствует профиль дистрибьютора", "Проверьте и восстановите профиль дистрибьютора перед сменой типа."),
    "leasing_applications": ("Заявки лизинговой компании", "Завершите или переназначьте связанные заявки."),
    "leasing_documents": ("Документы лизинговой компании", "Завершите обработку связанных документов."),
    "leasing_document_requirements": ("Требования к документам", "Удалите или перенастройте требования к документам."),
    "leasing_company_users": ("Пользователи лизинговой компании", "Переназначьте пользователей лизинговой компании."),
    "monetization": ("Программы и сделки монетизации", "Завершите или переназначьте связанные программы и сделки."),
    "leasing_contractors": ("Связи с подрядчиками", "Удалите или переназначьте связи с подрядчиками."),
    "leasing_support_programs": ("Программы поддержки лизинговой компании", "Завершите или переназначьте связанные программы поддержки."),
    "company_documents": ("Документы компании", "Завершите обработку связанных документов компании."),
    "distributor_brands": ("Марки дистрибьютора", "Удалите или переназначьте связанные марки."),
    "distributor_dealer_links": ("Связи дистрибьютора и дилеров", "Удалите или переназначьте связанные связи дистрибьютора и дилеров."),
    "dealer_groups": ("Группы дилеров", "Удалите или переназначьте связанные группы дилеров."),
    "distributor_warehouses": ("Склады дистрибьютора", "Переназначьте или закройте склады дистрибьютора."),
    "dealer_distribution_requests": ("Заявки на распределение дилерам", "Завершите или переназначьте связанные заявки."),
    "distributor_support_programs": ("Программы поддержки дистрибьютора", "Завершите или переназначьте связанные программы поддержки."),
    "dealer_applications": ("Заявки дилера", "Завершите или переназначьте связанные заявки дилера."),
    "dealer_inventory": ("Товарные позиции дилера", "Переназначьте или снимите с продажи товарные позиции дилера."),
    "dealer_warehouses": ("Склады дилера", "Переназначьте или закройте склады дилера."),
    "dealer_distributions": ("Распределения дилера", "Завершите или переназначьте связанные распределения."),
}


def _present_blockers(
    blockers: list[transition_repo.TypeTransitionBlocker],
) -> list[dict[str, str | int]]:
    """Attach safe Russian text while retaining stable machine-readable codes."""
    result: list[dict[str, str | int]] = []
    for blocker in blockers:
        code = blocker["code"]
        label, resolution_hint = _BLOCKER_PRESENTATION[code]
        result.append(
            {
                "code": code,
                "label": label,
                "count": int(blocker["count"]),
                "resolution_hint": resolution_hint,
            }
        )
    return result


class CompanyTypeTransitionConflictError(ServiceError):
    """A safe role-lifecycle refusal consumable by the admin HTTP contract."""

    def __init__(self, blockers: list[dict[str, str | int]]) -> None:
        labels = ", ".join(
            f"{blocker['label']} ({blocker['count']})" for blocker in blockers
        )
        super().__init__(
            "Смена типа компании невозможна: есть связанные данные "
            f"({labels}).",
            409,
            code="TYPE_TRANSITION_CONFLICT",
        )
        self.blockers = blockers


@dataclass(frozen=True)
class AdminUpdateCompanyCommand:
    company_id: UUID
    actor_id: UUID
    data: dict[str, Any] = field(default_factory=dict)


async def _transition_company_type(
    session: AsyncSession,
    *,
    company_id: UUID,
    target_type: str,
) -> None:
    """Apply the role lifecycle under a company-row lock, without committing."""
    if target_type not in _COMPANY_TYPES:
        raise ServiceError("Недопустимый тип компании", 422, code="VALIDATION_ERROR")

    state = await transition_repo.lock_company_type_transition_state(session, company_id)
    if state is None:
        raise CompanyNotFoundError()
    company, leasing_extension, distributor_extension = state
    current_type = str(company["company_type"])
    target_extension = (
        leasing_extension if target_type == "leasing_company" else distributor_extension
        if target_type == "distributor"
        else None
    )

    leaving_type = (
        current_type
        if current_type in _SPECIALIZED_TYPES and current_type != target_type
        else None
    )
    if leaving_type == "leasing_company" and leasing_extension is None:
        raise CompanyTypeTransitionConflictError(
            _present_blockers([{"code": "missing_leasing_extension", "count": 1}])
        )
    if leaving_type == "distributor" and distributor_extension is None:
        raise CompanyTypeTransitionConflictError(
            _present_blockers([{"code": "missing_distributor_extension", "count": 1}])
        )
    if leaving_type is not None:
        blockers = await transition_repo.list_type_transition_blockers(
            session,
            company_id=company_id,
            current_type=leaving_type,
            leasing_extension_id=(
                leasing_extension.get("id") if leasing_extension is not None else None
            ),
        )
        if blockers:
            raise CompanyTypeTransitionConflictError(_present_blockers(blockers))
    elif current_type == "dealer" and current_type != target_type:
        blockers = await transition_repo.list_type_transition_blockers(
            session,
            company_id=company_id,
            current_type=current_type,
            leasing_extension_id=None,
        )
        if blockers:
            raise CompanyTypeTransitionConflictError(_present_blockers(blockers))

    if current_type != target_type:
        await transition_repo.apply_company_type_transition(
            session,
            company_id=company_id,
            target_type=target_type,
            leaving_type=leaving_type,
            target_extension=target_extension,
        )


async def handle_admin_update_company(
    cmd: AdminUpdateCompanyCommand, session: AsyncSession
) -> dict[str, Any]:
    """Update admin fields; ``company_type`` follows the locked lifecycle only.

    The generic company command remains the source of truth for ordinary field
    validation and activation. Its unsafe generic type write is deliberately
    bypassed: the type is removed before delegation after the lifecycle
    transition has completed in this same uncommitted transaction. The event
    payload is returned for the router to publish only after its commit.
    """
    payload = {key: value for key, value in cmd.data.items() if key in _EDITABLE_FIELDS}
    if not payload:
        raise ServiceError("Передайте хотя бы одно изменённое поле", 422, code="VALIDATION_ERROR")
    before = await company_repo.get_company_by_id(session, cmd.company_id)
    if before is None:
        raise CompanyNotFoundError()
    changed = any(before.get(key) != value for key, value in payload.items())
    if not changed:
        return {"company": dict(before), "company_changed_event": None}

    target_type = payload.pop("company_type", None)
    if target_type is not None:
        await _transition_company_type(session, company_id=cmd.company_id, target_type=target_type)

    result = await handle_update_company(
        UpdateCompanyCommand(
            company_id=cmd.company_id, actor_id=cmd.actor_id, actor_role="carcraft_employee",
            data=payload, clear_null_fields=frozenset({"phone", "email", "website", "actual_address"}),
            emit_event=False,
        ), session,
    )
    company = result["company"]
    await history_repo.write_snapshot(
        session, company_id=cmd.company_id, actor_user_id=cmd.actor_id,
        action="company_profile_saved",
    )
    return {"company": company, "company_changed_event": build_company_changed_event(cmd.company_id, company)}

"""Клиент выбирает лизинговую компанию по итоговому КП (ТЗ №18, п. 2.10.2).

Переводит выбранный LeasingCompanyApplication в статус ``selected_lc``.
Остальные офферы заявки не трогаем — фронт деактивирует их кнопки сам,
а ЛК видят смену статуса выбранного оффера.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.dwh_enrichment import build_lca_payload
from application.notifications.leasing_events import record_leasing_event
from application.permissions import ensure_application_owned_by
from domain.entities.leasing_company_application import (
    LCA_STATUS_APPROVED_FINAL,
    LCA_STATUS_APPROVED_FINAL_ANOTHER_COND,
    LCA_STATUS_SELECTED_LC,
    LeasingCompanyApplication,
)
from domain.errors import (
    ApplicationNotFoundError,
    DomainError,
    InvalidLeasingCompanyApplicationStatusError,
    LeasingCompanyApplicationNotFoundError,
)
from infrastructure.messaging.dwh_events import emit_lca_changed
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.repositories import status_history_repository as hist_repo


@dataclass
class SelectLeasingCompanyCommand:
    application_id: uuid.UUID
    lca_id: UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None


async def handle_select_leasing_company(
    cmd: SelectLeasingCompanyCommand, session: AsyncSession
) -> dict[str, Any]:
    raw_app = await app_repo.get_by_id(session, cmd.application_id, for_update=True)
    if raw_app is None:
        raise ApplicationNotFoundError(cmd.application_id)
    await ensure_application_owned_by(
        session,
        application=raw_app,
        user_id=cmd.actor_id,
        actor_role=cmd.actor_role,
        actor_company_id=cmd.actor_company_id,
    )

    raw_link = await lca_repo.get_link_by_id(session, link_id=cmd.lca_id, for_update=True)
    if raw_link is None:
        raise LeasingCompanyApplicationNotFoundError(cmd.lca_id)
    if (
        raw_link.get("application_id")
        and uuid.UUID(str(raw_link["application_id"])) != cmd.application_id
    ):
        raise LeasingCompanyApplicationNotFoundError(cmd.lca_id)
    link = LeasingCompanyApplication.from_dict(raw_link)

    # ТЗ №18: выбрать ЛК можно только по итоговому одобрению. Легаси-переход
    # submitted → selected_lc в домене остаётся, но для клиентской команды
    # выбор разрешён исключительно из approved_final*.
    if link.status not in {
        LCA_STATUS_APPROVED_FINAL,
        LCA_STATUS_APPROVED_FINAL_ANOTHER_COND,
    }:
        raise InvalidLeasingCompanyApplicationStatusError(
            link.status, LCA_STATUS_SELECTED_LC
        )
    # ТЗ №18 п.2.10.2.2: по заявке можно выбрать только одну ЛК. Фронт
    # деактивирует кнопки сам, но от гонки (второй таб, отставший поллинг)
    # защищаемся и на сервере.
    statuses = await lca_repo.list_lca_statuses(session, cmd.application_id)
    if LCA_STATUS_SELECTED_LC in statuses:
        raise DomainError("По заявке уже выбрана лизинговая компания")
    link.ensure_can_change_status(LCA_STATUS_SELECTED_LC)
    await lca_repo.update_link_status(
        session,
        link_id=link.id,
        new_status=LCA_STATUS_SELECTED_LC,
    )
    await hist_repo.append_lca_status_history(
        session,
        lca_id=link.id,
        application_id=cmd.application_id,
        old_status=link.status,
        new_status=LCA_STATUS_SELECTED_LC,
        changed_by=cmd.actor_id,
    )

    updated_lca = await lca_repo.get_link_by_id(session, link.id)
    if updated_lca is not None:
        payload = await build_lca_payload(session, updated_lca, raw_app)
        emit_lca_changed(payload)

    for event_type in ("leasing.company_selected", "leasing.company_not_selected"):
        await record_leasing_event(
            session, application=raw_app, event_type=event_type,
            actor_user_id=cmd.actor_id,
            previous_values={"lca_status": link.status},
            new_values={"lca_status": LCA_STATUS_SELECTED_LC},
            payload={
                "leasing_company_id": link.leasing_company_id,
                "selected_leasing_company_id": link.leasing_company_id,
                "leasing_company_application_id": link.id,
            },
        )
    return {
        "application_id": cmd.application_id,
        "leasing_company_application_id": link.id,
        "status": LCA_STATUS_SELECTED_LC,
    }

"""Canonical contract for the leasing-company application status funnel.

The module is intentionally pure: domain status codes, report order and
human-readable labels live together without depending on presentation or
infrastructure layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domain.entities.leasing_company_application import (
    LCA_STATUS_APPROVED_FINAL,
    LCA_STATUS_APPROVED_FINAL_ANOTHER_COND,
    LCA_STATUS_APPROVED_SCORING,
    LCA_STATUS_APPROVED_SCORING_ANOTHER_COND,
    LCA_STATUS_CLOSED,
    LCA_STATUS_DEAL,
    LCA_STATUS_DOCUMENTS_REQUIRED,
    LCA_STATUS_REJECTED_APPROVED,
    LCA_STATUS_REJECTED_PRESCORING,
    LCA_STATUS_SELECTED_LC,
    LCA_STATUS_SUBMITTED,
    LCA_STATUS_UNDER_REVIEW,
    LCA_STATUS_UNDER_REVIEW_WITH_DOCS,
)


class ApplicationFunnelSelectionMode(StrEnum):
    """How leasing-company applications are selected for the report."""

    CREATED_IN_PERIOD = "created_in_period"
    ACTIVE_DURING_PERIOD = "active_during_period"


@dataclass(frozen=True, slots=True)
class ApplicationFunnelStatus:
    code: str
    label: str
    order: int


APPLICATION_FUNNEL_STATUSES: tuple[ApplicationFunnelStatus, ...] = (
    ApplicationFunnelStatus(LCA_STATUS_SUBMITTED, "Подана", 1),
    ApplicationFunnelStatus(LCA_STATUS_UNDER_REVIEW, "На рассмотрении", 2),
    ApplicationFunnelStatus(LCA_STATUS_DOCUMENTS_REQUIRED, "Требуются документы", 3),
    ApplicationFunnelStatus(
        LCA_STATUS_UNDER_REVIEW_WITH_DOCS,
        "На рассмотрении с доп. документами",
        4,
    ),
    ApplicationFunnelStatus(LCA_STATUS_APPROVED_SCORING, "Одобрено по скорингу", 5),
    ApplicationFunnelStatus(
        LCA_STATUS_APPROVED_SCORING_ANOTHER_COND,
        "Одобрено по скорингу на других условиях",
        6,
    ),
    ApplicationFunnelStatus(
        LCA_STATUS_REJECTED_PRESCORING,
        "Отказано на прескоринге",
        7,
    ),
    ApplicationFunnelStatus(LCA_STATUS_APPROVED_FINAL, "Финально одобрено", 8),
    ApplicationFunnelStatus(
        LCA_STATUS_APPROVED_FINAL_ANOTHER_COND,
        "Финально одобрено на других условиях",
        9,
    ),
    ApplicationFunnelStatus(
        LCA_STATUS_REJECTED_APPROVED,
        "Отказано после рассмотрения",
        10,
    ),
    ApplicationFunnelStatus(LCA_STATUS_SELECTED_LC, "Выбрана ЛК", 11),
    ApplicationFunnelStatus(LCA_STATUS_DEAL, "Профинансировано", 12),
    ApplicationFunnelStatus(LCA_STATUS_CLOSED, "Закрыто клиентом", 13),
)

APPLICATION_FUNNEL_STATUS_CODES: tuple[str, ...] = tuple(
    item.code for item in APPLICATION_FUNNEL_STATUSES
)

APPLICATION_FUNNEL_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        LCA_STATUS_DEAL,
        LCA_STATUS_CLOSED,
        LCA_STATUS_REJECTED_PRESCORING,
        LCA_STATUS_REJECTED_APPROVED,
    }
)

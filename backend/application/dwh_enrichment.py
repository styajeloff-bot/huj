"""DWH payload enrichment with denormalized names from DB lookups.

Builds on top of ``infrastructure.messaging.dwh_events.build_*`` helpers
and enriches the payloads with human-readable names (dealer, leasing
company, vehicle mark/model) before they are emitted to Kafka.

All lookups go through repositories; no session.commit() is called here.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from infrastructure.messaging.dwh_events import (
    build_lca_dwh_payload,
    build_proposal_dwh_payload,
)
from infrastructure.repositories import company_repository
from infrastructure.repositories import (
    special_equipment_commerce_repository as product_repo,
)


async def build_lca_payload(
    session: AsyncSession,
    lca_data: dict[str, Any],
    app_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build enriched DWH payload for LCA with denormalized names.

    Adds: dealer_name, dealer_city, leasing_company_name, mark_name,
    model_name, vehicle_mark_id, vehicle_model_id.
    """
    payload: dict[str, Any] = build_lca_dwh_payload(lca_data, app_data)

    # ── Dealer name / city ────────────────────────────────────────────
    dealer_company_id = payload.get("dealer_company_id")
    if dealer_company_id is not None:
        dealer = await company_repository.get_company_by_id(
            session, dealer_company_id
        )
        if dealer is not None:
            payload["dealer_name"] = dealer.get("name")
            payload["dealer_city"] = dealer.get("city")

    # ── Leasing company name ──────────────────────────────────────────
    # ``leasing_company_id`` is the ``leasing_companies.id`` PK; the helper
    # joins through to ``companies.name`` for the human-readable label.
    leasing_company_id = payload.get("leasing_company_id")
    if leasing_company_id is not None:
        payload["leasing_company_name"] = (
            await company_repository.get_leasing_company_name(
                session, leasing_company_id
            )
        )

    # ── Product mark / model ───────────────────────────────────────────
    product_id = payload.get("product_id") or payload.get("vehicle_id")
    if product_id is not None:
        product = await product_repo.get_product(session, product_id)
        if product is not None:
            payload["vehicle_mark_id"] = product.get("mark_id")
            payload["vehicle_model_id"] = product.get("model_id")
            payload["mark_name"] = product.get("mark_name")
            payload["model_name"] = product.get("model_name")

    # ── Normalise datetime fields ─────────────────────────────────────
    payload["response_pdf_uploaded_at"] = _isoformat(
        payload.get("response_pdf_uploaded_at")
    )
    payload["submitted_at"] = _isoformat(payload.get("submitted_at"))
    payload["created_at"] = _isoformat(payload.get("created_at"))
    payload["updated_at"] = _isoformat(payload.get("updated_at"))

    return payload


async def build_proposal_payload(
    session: AsyncSession,
    proposal_data: dict[str, Any],
    lca_data: dict[str, Any] | None = None,
    app_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build enriched DWH payload for LeasingProposal with denormalized names.

    Adds: dealer_name, dealer_city, leasing_company_name.
    """
    payload: dict[str, Any] = build_proposal_dwh_payload(
        proposal_data, lca_data, app_data
    )

    # ── Dealer name / city ────────────────────────────────────────────
    dealer_company_id = payload.get("dealer_company_id")
    if dealer_company_id is not None:
        dealer = await company_repository.get_company_by_id(
            session, dealer_company_id
        )
        if dealer is not None:
            payload["dealer_name"] = dealer.get("name")
            payload["dealer_city"] = dealer.get("city")

    # ── Leasing company name ──────────────────────────────────────────
    leasing_company_id = payload.get("leasing_company_id")
    if leasing_company_id is not None:
        ext = await company_repository.get_leasing_company_extension(
            session, leasing_company_id
        )
        if ext is not None:
            # The extension only carries the PK + stat fields, so also
            # look up the base company row for its human-readable name.
            lc_company = await company_repository.get_company_by_id(
                session, leasing_company_id
            )
            payload["leasing_company_name"] = (
                lc_company.get("name") if lc_company else None
            )

    # ── Normalise datetime fields ─────────────────────────────────────
    payload["client_decision_at"] = _isoformat(payload.get("client_decision_at"))
    payload["created_at"] = _isoformat(payload.get("created_at"))
    payload["updated_at"] = _isoformat(payload.get("updated_at"))

    return payload

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.signature_documents import _active_sopd_operator_data
from application.queries.signer_sopd_context import build_signer_context
from infrastructure.models.applications import (
    ApplicationQuestionnaire,
    LeasingApplication,
)
from infrastructure.models.companies import Company
from infrastructure.models.users import User
from infrastructure.services import sopd_revoke_renderer

pytestmark = pytest.mark.asyncio


async def test_build_signer_context_uses_application_questionnaire_director_fields(
    db_session: AsyncSession,
) -> None:
    user = User(
        phone="+76662150601",
        email="sopd-context@test.local",
        name="Петров Петр Петрович",
        role="client",
        is_active=True,
    )
    company = Company(name="ООО Тест СОПД", inn="9700000601", company_type="other")
    db_session.add_all([user, company])
    await db_session.flush()

    application = LeasingApplication(
        company_id=company.id,
        created_by=user.id,
        selected_leasing_companies=[],
    )
    db_session.add(application)
    await db_session.flush()

    questionnaire = ApplicationQuestionnaire(
        application_id=application.id,
        director_full_name="Петров Петр Петрович",
        director_birth_date=date(1980, 2, 1),
        director_birth_place="г. Саратов",
        director_passport_series="4512",
        director_passport_number="345678",
        director_passport_issued_by="ОВД Ленинского района г. Саратова",
        director_passport_issue_date=date(2014, 3, 12),
        director_passport_department_code="640-001",
        director_registration_address="410000, г. Саратов, ул. Тестовая, д. 1",
        director_phone="+76662150601",
        director_email="director@test.local",
    )
    db_session.add(questionnaire)
    await db_session.flush()

    context = await build_signer_context(
        db_session,
        user_id=user.id,
        subject_snapshot={
            "full_name": "Петров Петр Петрович",
            "inn": "770001506001",
            "phone": "+76662150601",
        },
        application_id=application.id,
    )

    assert context["full_name"] == "Петров Петр Петрович"
    assert context["birth_date"] == "01.02.1980"
    assert context["birth_place"] == "г. Саратов"
    assert context["passport_series_number"] == "4512 345678"
    assert context["passport_issued_by"] == "ОВД Ленинского района г. Саратова"
    assert context["passport_issued_at"] == "12.03.2014"
    assert context["passport_code"] == "640-001"
    assert context["address"] == "410000, г. Саратов, ул. Тестовая, д. 1"
    assert context["phone"] == "+76662150601"


def test_sopd_revoke_renderer_fills_docx_example_shape() -> None:
    html = sopd_revoke_renderer._build_html(
        {
            "subject": {
                "full_name": "Петров Петр Петрович",
                "address": "410000, г. Саратов, ул. Тестовая, д. 1",
                "passport_series_number": "4512 345678",
                "passport_issued_at": "12.03.2014",
                "passport_issued_by": "ОВД Ленинского района г. Саратова",
                "passport_code": "640-001",
                "phone": "+76662150601",
                "postal_address": "410000, г. Саратов, ул. Тестовая, д. 1",
            },
            "source_document": {
                "id": "4d833dd5-6540-43f0-9279-99e3b16eae92",
                "display_number": "7709401087-0622-001",
                "signed_at": datetime(2026, 6, 17, 12, 30, tzinfo=UTC),
            },
            "confirmed_at": datetime(2026, 6, 18, 17, 16, tzinfo=UTC),
            "operators": [
                {
                    "operator_type": "leasing_company",
                    "name": "Тестовая ЛК ВТБ для СОПД",
                    "inn": "7710000002",
                },
                {
                    "operator_type": "contractor",
                    "name": "АО Объединенное кредитное бюро",
                    "inn": "7701234567",
                    "leasing_companies": [
                        {
                            "name": "Тестовая ЛК ВТБ для СОПД",
                            "inn": "7710000002",
                        }
                    ],
                },
            ],
        }
    )

    assert "ОТЗЫВ СОГЛАСИЯ НА ОБРАБОТКУ ПЕРСОНАЛЬНЫХ ДАННЫХ" in html
    assert "Петров Петр Петрович" in html
    assert "паспорт серия <span class=\"field\">4512</span>" in html
    assert "№ <span class=\"field\">345678</span>" in html
    assert "СОПД № 7709401087-0622-001" in html
    assert "СОПД № 4d833dd5-6540-43f0-9279-99e3b16eae92" not in html
    assert "Тестовая ЛК ВТБ для СОПД, ИНН 7710000002" in html
    assert "АО Объединенное кредитное бюро, ИНН 7701234567" in html
    assert "подрядчик лизинговых компаний" in html
    assert "Операторы для отзыва не указаны" not in html
    assert "<table>" not in html


async def test_active_sopd_operator_data_excludes_revoked_lc_and_relinks_shared_contractor() -> None:
    reso = {
        "id": "21498000-0000-0000-0000-000000000201",
        "name": "Тестовая ЛК РЕСО для СОПД",
        "inn": "7710000001",
    }
    vtb = {
        "id": "21498000-0000-0000-0000-000000000202",
        "name": "Тестовая ЛК ВТБ для СОПД",
        "inn": "7710000002",
    }
    active = _active_sopd_operator_data(
        leasing_companies=[reso, vtb],
        contractors=[
            {
                "id": "21498000-0000-0000-0000-000000000301",
                "name": "АО Объединенное кредитное бюро",
                "inn": "7701234567",
                "leasing_company_ids": [reso["id"], vtb["id"]],
                "leasing_companies": [reso, vtb],
            },
            {
                "id": "21498000-0000-0000-0000-000000000303",
                "name": "ООО Архивный оператор ПД",
                "inn": "500100000001",
                "leasing_company_ids": [vtb["id"]],
                "leasing_companies": [vtb],
            },
        ],
        revoked_facts=[
            {
                "operator_type": "leasing_company",
                "leasing_company_id": vtb["id"],
            },
            {
                "operator_type": "contractor",
                "contractor_id": "21498000-0000-0000-0000-000000000303",
            },
        ],
    )

    assert active.leasing_companies == [reso]
    assert len(active.contractors) == 1
    assert active.contractors[0]["name"] == "АО Объединенное кредитное бюро"
    assert active.contractors[0]["leasing_company_ids"] == [reso["id"]]
    assert active.contractors[0]["leasing_companies"] == [reso]
    assert "Тестовая ЛК ВТБ для СОПД" not in active.leasing_companies_text
    assert "Тестовая ЛК ВТБ для СОПД" not in active.contractors_text

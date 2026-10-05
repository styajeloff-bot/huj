from typing import Any, cast

import pytest
from pytest import MonkeyPatch
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.leasing.document_request_forms import validate_form_data
from application.commands.leasing.request_documents import (
    RequestedDocument,
    _resolve_requested_documents,
)
from application.queries.documents.list_document_requests import (
    mask_form_data_for_actor,
)
from infrastructure.models.documents import ApplicationDocumentRequest, DocumentType


def test_optional_document_request_json_is_bound_as_sql_null() -> None:
    for column in (
        DocumentType.__table__.c.form_schema,
        ApplicationDocumentRequest.__table__.c.form_schema,
        ApplicationDocumentRequest.__table__.c.form_data,
    ):
        json_type = cast("postgresql.JSONB", column.type)
        assert json_type.none_as_null is True
        bind_processor = json_type.bind_processor(postgresql.dialect())
        assert bind_processor is None or bind_processor(None) is None


@pytest.mark.parametrize(
    ("kind", "data", "expected"),
    [
        ("snils", {"number": "123-456 789 01"}, {"number": "12345678901"}),
        ("beneficial_owner", {"fio": " Иван Иванов "}, {"fio": "Иван Иванов"}),
        (
            "main_counterparties",
            {"counterparties": [{"name": "ООО Ромашка", "inn": "7707083893"}]},
            {"counterparties": [{"name": "ООО Ромашка", "inn": "7707083893"}]},
        ),
        (
            "open_bank_accounts",
            {
                "accounts": [
                    {
                        "bank": {"name": "Банк", "bik": "044525225"},
                        "acc_number": "40702810000000000001",
                    }
                ]
            },
            {
                "accounts": [
                    {
                        "bank": {"name": "Банк", "bik": "044525225"},
                        "acc_number": "40702810000000000001",
                    }
                ]
            },
        ),
    ],
)
def test_valid_forms(kind: str, data: dict[str, Any], expected: dict[str, Any]) -> None:
    assert validate_form_data({"kind": kind}, data) == expected


@pytest.mark.parametrize(
    "kind,data",
    [
        ("snils", {"number": "1234567890x"}),
        ("beneficial_owner", {"fio": "", "extra": "x"}),
        ("main_counterparties", {"counterparties": [{"name": "x", "inn": "123"}]}),
        (
            "open_bank_accounts",
            {"accounts": [{"bank": {"name": "x", "bik": "1"}, "acc_number": "1"}]},
        ),
    ],
)
def test_forms_reject_invalid_and_extra_keys(kind: str, data: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        validate_form_data({"kind": kind}, data)


def test_client_snils_mask_hides_all_but_last_two_digits() -> None:
    assert mask_form_data_for_actor({"number": "12345678901"}, "client") == {
        "number": "***-***-*** 01"
    }
    assert mask_form_data_for_actor({"number": "12345678901"}, "leasing_company") == {
        "number": "12345678901"
    }


@pytest.mark.asyncio
async def test_catalog_request_preserves_lc_display_name_and_catalog_snapshot(
    monkeypatch: MonkeyPatch,
) -> None:
    async def get_by_type_code(
        _session: AsyncSession, type_code: str
    ) -> dict[str, Any]:
        assert type_code == "snils"
        return {
            "type_code": "snils",
            "display_name": "СНИЛС из каталога",
            "has_form": True,
            "form_schema": {"kind": "snils"},
        }

    monkeypatch.setattr(
        "application.commands.leasing.request_documents.types_repo.get_by_type_code",
        get_by_type_code,
    )
    resolved = await _resolve_requested_documents(
        cast("AsyncSession", object()),
        [
            RequestedDocument(
                source="catalog",
                document_type="snils",
                display_name="СНИЛС директора",
            )
        ],
    )

    assert resolved[0].display_name == "СНИЛС директора"
    assert resolved[0].slug == "snils"
    assert resolved[0].has_form is True
    assert resolved[0].form_schema == {"kind": "snils"}


@pytest.mark.asyncio
async def test_catalog_vat_and_custom_request_resolve_to_persistable_snapshots(
    monkeypatch: MonkeyPatch,
) -> None:
    async def get_by_type_code(
        _session: AsyncSession, type_code: str
    ) -> dict[str, Any]:
        assert type_code == "vat_declaration_xml"
        return {
            "type_code": "vat_declaration_xml",
            "display_name": "Декларация по НДС",
            "has_form": False,
            "form_schema": None,
        }

    monkeypatch.setattr(
        "application.commands.leasing.request_documents.types_repo.get_by_type_code",
        get_by_type_code,
    )
    resolved = await _resolve_requested_documents(
        cast("AsyncSession", object()),
        [
            RequestedDocument(
                source="catalog",
                document_type="vat_declaration_xml",
                display_name="Декларация по НДС",
            ),
            RequestedDocument(source="custom", display_name="Дополнительный документ"),
        ],
    )

    assert [(item.slug, item.has_form, item.form_schema) for item in resolved] == [
        ("vat_declaration_xml", False, None),
        ("custom_document", False, None),
    ]
